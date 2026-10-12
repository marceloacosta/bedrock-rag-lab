"""Generate review packets, metrics, and an answer viewer from saved traces."""
import copy
import argparse
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import sys
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RECORDED = ROOT/'measurements/recorded'
SOURCE = RECORDED
OUT = None
VIEWER = None
sys.path.insert(0, str(ROOT))
from support import write_json, fingerprint


def trials():
    rows = []
    cases = {c['id']:c for c in json.loads((ROOT/'data/cases.json').read_text())}
    for p in sorted((SOURCE/'run').glob('*--*.json')):
        raw = json.loads(p.read_text())
        if raw['status'] != 'completed':
            continue
        t = copy.deepcopy(raw)
        t['source_trace'] = str(p.relative_to(ROOT))
        t['source_sha256'] = fingerprint(p)
        t.pop('attempted_calls', None)
        final_request = raw['calls'][-1]['request']
        t['final_prompt_mode'] = ('fresh_evidence_prompt' if len(final_request['messages']) == 1
                                  and 'toolConfig' not in final_request else 'conversation')
        if raw['variant'] == 'adaptive' and 'toolConfig' in final_request:
            t['final_prompt_mode'] = 'search_conversation'
        if raw['variant'] == 'reconsider':
            first = copy.deepcopy(t)
            first.update(id=raw['case_id']+'--initial_three', variant='initial_three',
                answer=raw['initial_answer'], citations_exist=raw['initial_citations_exist'],
                calls=raw['calls'][:1], estimated_model_usd=raw['calls'][0]['estimated_model_usd'],
                api_seconds=raw['calls'][0]['api_seconds']+raw['searches'][0]['api_seconds'])
            first.pop('elapsed_seconds',None)
            first.pop('raw_answer',None)
            first['final_prompt_mode'] = 'fresh_evidence_prompt'
            rows.append(first)
        rows.append(t)
    for t in rows:
        c = cases[t['case_id']]
        supplied = '\n'.join(p['text'] for p in t['evidence']).casefold()
        cited_ids = set(t['answer']['citations'])
        cited = '\n'.join(p['text'] for p in t['evidence'] if p['id'] in cited_ids).casefold()
        initial = '\n'.join(p['text'] for p in t['searches'][0]['chunks']).casefold() if t['searches'] else supplied
        t['evidence_diagnostic'] = {'required_phrases':c['facts'],
            'initial_hits':[f.casefold() in initial for f in c['facts']],
            'final_hits':[f.casefold() in supplied for f in c['facts']],
            'cited_hits':[f.casefold() in cited for f in c['facts']]}
        t['input_tokens'] = sum(c['usage']['inputTokens'] for c in t['calls'])
        t['output_tokens'] = sum(c['usage']['outputTokens'] for c in t['calls'])
        t['model_calls'] = len(t['calls'])
    return rows


def packets(rows):
    result = []
    for t in rows:
        key = hashlib.sha256(('answer-review:'+t['id']).encode()).hexdigest()[:10]
        result.append({'packet_id':key, 'case_id':t['case_id'], 'question':t['question'],
            'source_sha256':t['source_sha256'],
            'answer':t['answer'], 'cited_sources': sorted({p['source'] for p in t['evidence'] if p['id'] in t['answer']['citations']}),
            'cited_phrase_hits':t['evidence_diagnostic']['cited_hits'],
            'citations_exist':t['citations_exist']})
    random.Random(12911).shuffle(result)
    write_json(OUT/'review-packets.json', result)
    write_json(OUT/'review-key.json', {hashlib.sha256(('answer-review:'+t['id']).encode()).hexdigest()[:10]:t['id'] for t in rows})
    return result


def build():
    if OUT is None or VIEWER is None:
        raise ValueError('Choose output paths through the CLI before building')
    rows = trials()
    packet = packets(rows)
    if not (SOURCE/'run/complete.json').exists():
        print(json.dumps({'completed_outputs':len(rows),'packets_prepared':len(packet),'run_complete':False}))
        return
    assert len(rows) == 120
    if not (SOURCE/'review.json').exists():
        print(json.dumps({'packets_prepared':len(packet),'review_pending':True}))
        return
    reviews = json.loads((SOURCE/'review.json').read_text())
    by_key = {r['packet_id']:r for r in reviews['judgments']}
    if len(by_key)<120:
        print(json.dumps({'packets_prepared':len(packet),'reviewed':len(by_key),'review_pending':True}))
        return
    assert len(by_key)==120
    for t in rows:
        key = hashlib.sha256(('answer-review:'+t['id']).encode()).hexdigest()[:10]
        t['review'] = by_key[key]
        assert t['review']['source_sha256']==t['source_sha256']
    variants = {}
    for v in ['initial_three','reconsider','fixed','adaptive','all_documents']:
        group = [t for t in rows if t['variant']==v]
        variants[v] = {'attempts':len(group), 'passed':sum(t['review']['pass'] for t in group),
            'estimated_model_usd':sum(t['estimated_model_usd'] for t in group),
            'median_api_seconds':statistics.median(t['api_seconds'] for t in group),
            'input_tokens':sum(t['input_tokens'] for t in group), 'output_tokens':sum(t['output_tokens'] for t in group),
            'model_calls':sum(t['model_calls'] for t in group),
            'searches':sum(len(t['searches']) for t in group),
            'full_phrase_coverage':sum(all(t['evidence_diagnostic']['final_hits']) for t in group),
            'by_kind':{kind:{'attempts':sum(t['kind']==kind for t in group),'passed':sum(t['kind']==kind and t['review']['pass'] for t in group)} for kind in ['direct','combined','missing']}}
    actual_rows=[t for t in rows if t['variant']!='initial_three']
    pilot=[json.loads(p.read_text()) for p in (SOURCE/'pilot').glob('*--*.json')]
    summary={'variants':variants,'scored_outputs':120,'evaluation_traces':96,
        'evaluation_model_usd':sum(t['estimated_model_usd'] for t in actual_rows),
        'evaluation_model_calls':sum(t['model_calls'] for t in actual_rows),
        'pilot_model_usd':sum(t['estimated_model_usd'] for t in pilot),
        'baseline_shared_with_reconsideration':True,'scorer':reviews['reviewer'],
        'fresh_adaptive_final_cases':sorted(t['case_id'] for t in rows if t['variant']=='adaptive' and t['final_prompt_mode']=='fresh_evidence_prompt'),
        'reconsider_answer_text_changes':sum(t['answer']['answer']!=t['initial_answer']['answer'] for t in rows if t['variant']=='reconsider')}
    write_json(OUT/'summary.json',summary)
    write_json(OUT/'trials.json',rows)
    stream=io.StringIO();writer=csv.DictWriter(stream,lineterminator='\n',fieldnames=['id','case_id','variant','kind','pass','reason','api_seconds','estimated_model_usd','input_tokens','output_tokens','model_calls','searches','source_sha256'])
    writer.writeheader()
    for t in rows:
        writer.writerow({**{k:t[k] for k in ['id','case_id','variant','kind','api_seconds','estimated_model_usd','input_tokens','output_tokens','model_calls','source_sha256']},'pass':t['review']['pass'],'reason':t['review']['reason'],'searches':len(t['searches'])})
    (OUT/'trials.csv').write_text(stream.getvalue())
    cases=[c for c in json.loads((ROOT/'data/cases.json').read_text()) if c['split']=='evaluation']
    # The viewer needs evidence and answers, not repeated request payloads.
    viewer=[{k:v for k,v in t.items() if k not in ['calls','raw_answer','initial_answer','initial_citations_exist']} for t in rows]
    development=json.loads((SOURCE/'development.json').read_text())
    data={'summary':summary,'cases':cases,'trials':viewer,'selected_k':development['selected_k'],
          'repository_base':os.path.relpath(ROOT,VIEWER).replace(os.sep,'/')+'/',
          'development':development['depth_scores']}
    VIEWER.mkdir(parents=True,exist_ok=True)
    if VIEWER != ROOT/'explorer':
        for name in ['app.js','style.css']:
            shutil.copy2(ROOT/'explorer'/name,VIEWER/name)
        page=(ROOT/'explorer/index.html').read_text()
        if SOURCE!=RECORDED:
            page=page.replace('RAG experiment results','Report from saved run · '+html.escape(SOURCE.name))
            provenance='Reviewer: '+str(reviews.get('reviewer','unspecified'))+'. '+str(reviews.get('blinding','Blinding not specified.'))+' These are the same known diagnostic questions; the baseline shares its first call with reconsideration.'
            page=re.sub(r'<p class="review-provenance small">.*?</p>',lambda m:'<p class="review-provenance small">'+html.escape(provenance)+'</p>',page)
            coverage=', '.join(str(s['k'])+' passages: '+str(s['complete_cases'])+' complete cases' for s in development['depth_scores'])
            page=re.sub(r'<p><strong>Nine passages:</strong>.*?</p>',lambda m:'<p><strong>Selected fixed depth: '+str(development['selected_k'])+' passages.</strong> Development coverage: '+coverage+'.</p>',page)
        def move_link(match):
            target=match.group(1)
            if urlsplit(target).scheme or target.startswith('#') or target in ['app.js','data.js','style.css']:
                return match.group(0)
            return 'href="'+os.path.relpath(ROOT/'explorer'/target,VIEWER).replace(os.sep,'/')+'"'
        page=re.sub(r'href="([^"]+)"',move_link,page)
        (VIEWER/'index.html').write_text(page)
    (VIEWER/'data.js').write_text('window.REVISION_DATA = '+json.dumps(data,ensure_ascii=False).replace('</','<' + chr(92) + '/')+';\n')
    print(json.dumps(summary,indent=2))


def main():
    global SOURCE, OUT, VIEWER
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,default=RECORDED)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--refresh-recorded',action='store_true',
                        help='Explicitly rebuild the recorded derived reports and the main viewer')
    args=parser.parse_args()
    SOURCE=args.run_dir.resolve()
    if not (SOURCE/'run').is_dir():
        parser.error('Run directory has no saved execution traces')
    if args.refresh_recorded:
        if SOURCE!=RECORDED or args.output_dir:
            parser.error('--refresh-recorded only accepts the original recorded dataset and no output override')
        OUT=RECORDED
        VIEWER=ROOT/'explorer'
    else:
        OUT=(args.output_dir or ROOT/'results'/('report-'+uuid.uuid4().hex[:12])).resolve()
        if OUT==SOURCE or SOURCE in OUT.parents or OUT==ROOT/'explorer' or ROOT/'explorer' in OUT.parents:
            parser.error('Reports must be separate from source measurements and the main viewer')
        if OUT==ROOT/'measurements' or ROOT/'measurements' in OUT.parents:
            parser.error('Choose a report directory outside measurements')
        OUT.mkdir(parents=True,exist_ok=False)
        VIEWER=OUT/'viewer'
    build()


if __name__=='__main__':main()
