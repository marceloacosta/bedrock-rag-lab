"""Provision and remove the S3 Vectors knowledge base used by the experiment."""
import json
from pathlib import Path
import time
import uuid

EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0'


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')
    path.chmod(0o600)


def provision(lab, state_path):
    state_path = Path(state_path)
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        name = 'rag-search-lab-' + uuid.uuid4().hex[:10]
        state = {'name': name, 'region': lab.config['region'],
                 'account': lab.config['expected_account_id'], 'index_name': 'support-passages'}
        save(state_path, state)
    account, region, name = state['account'], state['region'], state['name']
    if account != lab.config['expected_account_id'] or region != lab.config['region']:
        raise RuntimeError('Resource state does not match the verified lab.')
    tags = [{'Key': 'Project', 'Value': 'rag-search-lab'}, {'Key': 'Purpose', 'Value': 'temporary-experiment'}]
    if not state.get('source_bucket'):
        lab.call('s3', 'create_bucket', Bucket=name,
                 CreateBucketConfiguration={'LocationConstraint': region})
        state['source_bucket'] = name
        save(state_path, state)
    lab.call('s3', 'put_public_access_block', Bucket=name, ExpectedBucketOwner=account,
             PublicAccessBlockConfiguration={k: True for k in
                 ['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets']})
    lab.call('s3', 'put_bucket_tagging', Bucket=name, ExpectedBucketOwner=account, Tagging={'TagSet': tags})
    lab.call('s3', 'put_bucket_encryption', Bucket=name, ExpectedBucketOwner=account,
             ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
    if not state.get('vector_bucket_arn'):
        response = lab.call('s3vectors', 'create_vector_bucket', vectorBucketName=name,
                            encryptionConfiguration={'sseType': 'AES256'},
                            tags={'Project': 'rag-search-lab'})
        state['vector_bucket_arn'] = response['vectorBucketArn']
        save(state_path, state)
    if not state.get('index_arn'):
        response = lab.call('s3vectors', 'create_index', vectorBucketName=name,
                            indexName=state['index_name'], dataType='float32', dimension=1024,
                            distanceMetric='cosine', metadataConfiguration={
                                'nonFilterableMetadataKeys': ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA']})
        state['index_arn'] = response['indexArn']
        save(state_path, state)
    trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
        'Principal': {'Service': 'bedrock.amazonaws.com'}, 'Action': 'sts:AssumeRole',
        'Condition': {'StringEquals': {'aws:SourceAccount': account},
                      'ArnLike': {'AWS:SourceArn': f'arn:aws:bedrock:{region}:{account}:knowledge-base/*'}}}]}
    if not state.get('role_arn'):
        role = lab.call('iam', 'create_role', RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Tags=tags)
        state['role_arn'] = role['Role']['Arn']
        save(state_path, state)
    policy = {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': ['s3:ListBucket'], 'Resource': f'arn:aws:s3:::{name}',
         'Condition': {'StringEquals': {'aws:ResourceAccount': account}}},
        {'Effect': 'Allow', 'Action': ['s3:GetObject'], 'Resource': f'arn:aws:s3:::{name}/documents/*',
         'Condition': {'StringEquals': {'aws:ResourceAccount': account}}},
        {'Effect': 'Allow', 'Action': ['bedrock:InvokeModel'],
         'Resource': f'arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL}'},
        {'Effect': 'Allow', 'Action': ['s3vectors:PutVectors', 's3vectors:GetVectors',
            's3vectors:DeleteVectors', 's3vectors:QueryVectors', 's3vectors:GetIndex'], 'Resource': state['index_arn']}]}
    lab.call('iam', 'put_role_policy', RoleName=name, PolicyName='KnowledgeBaseData', PolicyDocument=json.dumps(policy))
    if not state.get('knowledge_base_id'):
        time.sleep(8)
        response = lab.call('bedrock-agent', 'create_knowledge_base', name='support-search-lab',
            clientToken=name + '-create-knowledge-base', roleArn=state['role_arn'],
            description='Compare one retrieval with bounded follow-up searches over support articles.',
            knowledgeBaseConfiguration={'type': 'VECTOR', 'vectorKnowledgeBaseConfiguration': {
                'embeddingModelArn': f'arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL}',
                'embeddingModelConfiguration': {'bedrockEmbeddingModelConfiguration': {'dimensions': 1024, 'embeddingDataType': 'FLOAT32'}}}},
            storageConfiguration={'type': 'S3_VECTORS', 's3VectorsConfiguration': {'indexArn': state['index_arn']}},
            tags={'Project': 'rag-search-lab'})
        state['knowledge_base_id'] = response['knowledgeBase']['knowledgeBaseId']
        save(state_path, state)
    trust['Statement'][0]['Condition']['ArnLike']['AWS:SourceArn'] = f"arn:aws:bedrock:{region}:{account}:knowledge-base/{state['knowledge_base_id']}"
    lab.call('iam', 'update_assume_role_policy', RoleName=name, PolicyDocument=json.dumps(trust))
    print(json.dumps({'provisioned': True, 'region': region, 'storage': 'S3_VECTORS',
                      'embedding_model': EMBEDDING_MODEL, 'account_matches': True}), flush=True)
    return state


def ingest(lab, state_path, corpus_dir):
    state = json.loads(Path(state_path).read_text())
    if state['account'] != lab.config['expected_account_id']:
        raise RuntimeError('Resource account mismatch')
    files = sorted(Path(corpus_dir).glob('*.txt'))
    if not files or sum(f.stat().st_size for f in files) > 1_000_000:
        raise ValueError('Expected a nonempty corpus smaller than 1 MB')
    for file in files:
        lab.call('s3', 'put_object', Bucket=state['source_bucket'], Key='documents/' + file.name,
                 Body=file.read_bytes(), ContentType='text/plain', ExpectedBucketOwner=state['account'])
    if not state.get('data_source_id'):
        response = lab.call('bedrock-agent', 'create_data_source', knowledgeBaseId=state['knowledge_base_id'],
            name='support-articles', clientToken=state['name'] + '-create-data-source', dataDeletionPolicy='DELETE',
            dataSourceConfiguration={'type': 'S3', 's3Configuration': {
                'bucketArn': f"arn:aws:s3:::{state['source_bucket']}",
                'bucketOwnerAccountId': state['account'], 'inclusionPrefixes': ['documents/']}},
            vectorIngestionConfiguration={'chunkingConfiguration': {'chunkingStrategy': 'FIXED_SIZE',
                'fixedSizeChunkingConfiguration': {'maxTokens': 200, 'overlapPercentage': 15}}})
        state['data_source_id'] = response['dataSource']['dataSourceId']
        save(Path(state_path), state)
    job = lab.call('bedrock-agent', 'start_ingestion_job', knowledgeBaseId=state['knowledge_base_id'],
                   dataSourceId=state['data_source_id'], clientToken=state['name'] + '-ingest-v1')['ingestionJob']
    state['ingestion_job_id'] = job['ingestionJobId']
    save(Path(state_path), state)
    print(json.dumps({'documents_uploaded': len(files), 'ingestion_status': job['status']}), flush=True)


def status(lab, state_path):
    state = json.loads(Path(state_path).read_text())
    if state['account'] != lab.config['expected_account_id']:
        raise RuntimeError('Resource account mismatch')
    kb = lab.call('bedrock-agent', 'get_knowledge_base', knowledgeBaseId=state['knowledge_base_id'])['knowledgeBase']
    result = {'knowledge_base_status': kb['status'], 'region': state['region'], 'account_matches': True}
    if state.get('ingestion_job_id'):
        job = lab.call('bedrock-agent', 'get_ingestion_job', knowledgeBaseId=state['knowledge_base_id'],
                       dataSourceId=state['data_source_id'], ingestionJobId=state['ingestion_job_id'])['ingestionJob']
        result.update(ingestion_status=job['status'], statistics=job.get('statistics', {}))
        if job.get('failureReasons'):
            save(Path(state_path).with_name('kb-ingestion-error.json'), job)
            result['failure_details_saved_privately'] = True
    print(json.dumps(result), flush=True)
    return result
