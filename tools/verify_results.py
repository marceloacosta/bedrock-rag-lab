"""Verify the supplied answers, source hashes, token costs, and paired comparisons."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'measurements/recorded'
def load(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

manifest=load(DATA/'files.json')
for name,wanted in manifest['files'].items():
    assert digest(ROOT/name)==wanted, f'File changed: {name}'
raw=[load(p) for p in (DATA/'run').glob('*--*.json')]
assert len(raw)==96 and all(t['status']=='completed' for t in raw)
assert Counter(t['variant'] for t in raw)==dict.fromkeys(['fixed','adaptive','all_documents','reconsider'],24)
rows=load(DATA/'trials.json');assert len(rows)==120
reviews=load(DATA/'review.json');assert len(reviews['judgments'])==120
assert digest(ROOT/reviews['rubric'])==reviews['rubric_sha256']
assert reviews['independent'] is False
summary=load(DATA/'summary.json')
for t in raw:
    for call in t['calls']:
        expected=(call['usage']['inputTokens']+call['usage']['outputTokens']*3.2)/1_000_000
        assert math.isclose(expected,call['estimated_model_usd'],abs_tol=1e-12)
        assert call['request']['modelId']=='zai.glm-5'
        assert call['request']['inferenceConfig']=={'maxTokens':600,'temperature':0}
    assert len(t['calls'])<=3 and len(t['searches'])<=3
    if t['variant']=='reconsider':
        assert len(t['calls'])==2 and len(t['searches'])==1
        assert t['calls'][0]['request']['messages'][0]==t['calls'][1]['request']['messages'][0]
    if t['variant']=='all_documents':assert len(t['evidence'])==24 and not t['searches']
    if t['variant']=='fixed':assert t['searches'][0]['requested_k']==9
    assert math.isclose(sum(c['estimated_model_usd'] for c in t['calls']),t['estimated_model_usd'],abs_tol=1e-12)
    assert math.isclose(sum(c['api_seconds'] for c in t['calls'])+sum(s['api_seconds'] for s in t['searches']),t['api_seconds'],abs_tol=1e-9)
for t in rows:
    assert digest(ROOT/t['source_trace'])==t['source_sha256']==t['review']['source_sha256']
    assert t['answer']['citations']
    if t['review']['pass']:assert t['citations_exist'],t['id']
for variant,s in summary['variants'].items():
    group=[t for t in rows if t['variant']==variant]
    assert s['passed']==sum(t['review']['pass'] for t in group)
    assert s['attempts']==len(group)==24
    assert math.isclose(s['estimated_model_usd'],sum(t['estimated_model_usd'] for t in group),abs_tol=1e-12)
    assert math.isclose(s['median_api_seconds'],statistics.median(t['api_seconds'] for t in group),abs_tol=1e-12)
assert math.isclose(summary['evaluation_model_usd'],sum(t['estimated_model_usd'] for t in raw),abs_tol=1e-12)
assert summary['evaluation_model_calls']==sum(len(t['calls']) for t in raw)==141
assert summary['baseline_shared_with_reconsideration'] is True
assert len(summary['fresh_adaptive_final_cases'])==9
for cid in {t['case_id'] for t in rows}:
    by={t['variant']:t for t in rows if t['case_id']==cid}
    assert by['initial_three']['source_trace']==by['reconsider']['source_trace']
    assert by['initial_three']['answer']==by['reconsider']['initial_answer']
    assert [p['id'] for p in by['initial_three']['searches'][0]['chunks']]==[p['id'] for p in by['adaptive']['searches'][0]['chunks']]
print('Verified 96 execution records, 120 scored answers, hashes, costs, timings, and paired controls.')
