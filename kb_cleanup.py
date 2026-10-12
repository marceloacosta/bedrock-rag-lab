"""Remove only resources recorded by this lab's provisioner."""
import json
from pathlib import Path
import re

from knowledge_base import save


def cleanup(lab, state_path):
    path = Path(state_path)
    state = json.loads(path.read_text())
    if state['account'] != lab.config['expected_account_id'] or state['region'] != lab.config['region']:
        raise RuntimeError('Resource state does not match this account and region')
    name = state['name']
    if not re.fullmatch(r'rag-search-lab-[a-f0-9]{10}', name) or state['source_bucket'] != name:
        raise ValueError('Resource names do not match the provisioner')
    done = state.setdefault('cleanup', [])

    def step(key, service, method, **parameters):
        if key in done:
            return
        try:
            lab.call(service, method, **parameters)
        except Exception as exc:
            code = getattr(exc, 'response', {}).get('Error', {}).get('Code')
            if code not in ['ResourceNotFoundException', 'NoSuchEntity', 'NoSuchBucket', 'NotFoundException']:
                raise
        done.append(key)
        save(path, state)
        print(json.dumps({'removed': key}), flush=True)

    step('knowledge_base', 'bedrock-agent', 'delete_knowledge_base', knowledgeBaseId=state['knowledge_base_id'])
    try:
        response = lab.call('bedrock-agent', 'get_knowledge_base', knowledgeBaseId=state['knowledge_base_id'])
    except Exception as exc:
        if getattr(exc, 'response', {}).get('Error', {}).get('Code') != 'ResourceNotFoundException':
            raise
    else:
        print(json.dumps({'cleanup_pending': True, 'knowledge_base_status': response['knowledgeBase']['status'],
                          'next_step': 'Run cleanup again after Knowledge Base deletion finishes.'}), flush=True)
        return
    step('vector_index', 's3vectors', 'delete_index', vectorBucketName=name, indexName=state['index_name'])
    step('vector_bucket', 's3vectors', 'delete_vector_bucket', vectorBucketName=name)
    if 'source_bucket' not in done:
        page = lab.call('s3', 'list_objects_v2', Bucket=name, ExpectedBucketOwner=state['account'])
        if page.get('IsTruncated'):
            raise RuntimeError('Unexpected object count; refusing bulk cleanup')
        keys = [o['Key'] for o in page.get('Contents', [])]
        if any(not key.startswith('documents/') for key in keys):
            raise RuntimeError('Unexpected objects in lab bucket')
        if keys:
            response = lab.call('s3', 'delete_objects', Bucket=name, ExpectedBucketOwner=state['account'],
                               Delete={'Objects': [{'Key': k} for k in keys], 'Quiet': True})
            if response.get('Errors'):
                raise RuntimeError('Some lab source objects could not be removed')
        step('source_bucket', 's3', 'delete_bucket', Bucket=name, ExpectedBucketOwner=state['account'])
    step('role_policy', 'iam', 'delete_role_policy', RoleName=name, PolicyName='KnowledgeBaseData')
    step('service_role', 'iam', 'delete_role', RoleName=name)
    print(json.dumps({'cleanup_complete': True, 'account_matches': True, 'removed_resources': done}), flush=True)
