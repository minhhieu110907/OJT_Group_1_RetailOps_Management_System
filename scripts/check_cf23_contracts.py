"""Kiểm tra tĩnh CF-2.3; không thay thế chạy FastAPI, MySQL hoặc E2E thực tế.

Chạy từ thư mục gốc ZIP (có README.md), hoặc repository sau khi đã chép docs/contracts/scripts: python scripts/check_cf23_contracts.py
Dependencies: PyYAML, jsonschema. No network/database required.
"""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict, deque
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
spec = yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text(encoding='utf-8'))
assert spec['openapi'].startswith('3.0.'), 'Cần OpenAPI 3.0'
schemas = spec['components']['schemas']
ops = {(path,verb): op for path,info in spec['paths'].items()
       for verb,op in info.items() if verb in ('get','post','put','patch','delete')}
assert len(ops)==29, f'Không được vô tình đổi số operation: {len(ops)}'
opids=[op['operationId'] for op in ops.values()]
assert len(opids)==len(set(opids)), 'Trùng operationId'
for item in ops.values():
    assert item.get('x-implementation-status') and item.get('x-owner-consumer-signoff')
    for ref in re.findall(r'#/components/schemas/([A-Za-z0-9_]+)',str(item)):
        assert ref in schemas, ref
for k,item in schemas.items():
    for ref in re.findall(r'#/components/schemas/([A-Za-z0-9_]+)',str(item)):
        assert ref in schemas, (k,ref)

# Product actual router baseline: verified source code snapshot on develop, NOT live API runtime.
baseline=json.loads((ROOT/'contracts/develop_product_api_baseline.json').read_text(encoding='utf-8'))
assert baseline['commit_sha']==ops[('/products','get')]['x-runtime-baseline-sha']
product_query={p['name']:p['schema'] for p in ops[('/products','get')]['parameters']}
assert set(product_query)==set(baseline['parameters']), (product_query, baseline['parameters'])
assert product_query['search']['maxLength']==baseline['parameters']['search']['maxLength']
assert product_query['sort']['enum']==baseline['parameters']['sort']['enum']
assert product_query['sort']['default']=='created_desc'
assert not any(p['name']=='q' for p in ops[('/products','get')]['parameters'])

# All required read filters in SRS.
for path,names in {
 '/purchase-receipts':{'status','supplier_id','from_date','to_date','page','page_size'},
 '/orders':{'status','search','from_date','to_date','page','page_size'},
 '/inventory':{'category_id','status','in_stock','page','page_size'},
 '/stock-movements':{'kind','product_id','page','page_size'}
}.items():
    actual={p['name'] for p in ops[(path,'get')]['parameters']}
    assert names<=actual,(path,names-actual)

# Role-specific schema prevents staff receiving the admin's audit fields.
assert 'StockMovementAdminRead' in schemas and 'StockMovementAdminPage' in schemas
assert 'actor_id' not in schemas['StockMovementRead']['properties']
assert 'adjustment_reason' not in schemas['StockMovementRead']['properties']

# Typed checkout PRICE_CHANGED and other 409s are disjoint by code.
sch=ops[('/orders/checkout','post')]['responses']['409']['content']['application/json']['schema']
assert sch['oneOf']==[{'$ref':'#/components/schemas/PriceChangedError'}, {'$ref':'#/components/schemas/CheckoutConflictError'}]
for path,method in [('/orders/checkout','post'),('/orders/{order_id}/cancel','post'),
                    ('/purchase-receipts/{receipt_id}/confirm','post'),('/inventory/{product_id}/adjustments','post')]:
    op=ops[(path,method)]
    assert op['x-idempotency']['single_mysql_transaction'] is True
    assert any(p['name']=='Idempotency-Key' and p['required'] for p in op.get('parameters',[]))

# OpenAPI 3 nullable is not JSON Schema Draft7; convert before fixtures validation.
def as_draft7(v):
    if isinstance(v,list): return [as_draft7(x) for x in v]
    if not isinstance(v,dict): return v
    out={k:as_draft7(x) for k,x in v.items() if k!='nullable'}
    if v.get('nullable') is True:
        if '$ref' in out: return {'anyOf':[out,{'type':'null'}]}
        if 'type' in out and isinstance(out['type'],str):out['type']=[out['type'],'null']
        elif 'anyOf' in out:out['anyOf'].append({'type':'null'})
        else:out={'anyOf':[out,{'type':'null'}]}
    return out

converted={k:as_draft7(v) for k,v in schemas.items()}
store={'#/components/schemas/'+k:v for k,v in converted.items()}
for name,sch in converted.items():
    Draft7Validator.check_schema(sch)
validator=lambda name: Draft7Validator({'components':{'schemas':converted}, '$ref':'#/components/schemas/'+name},
                                  format_checker=FormatChecker())

fixture_mapping={
 'receipt_create_request.json':'ReceiptCreateRequest',
 'sales_summary_200.json':'SalesSummary',
 'inventory_adjust_request.json':'AdjustRequest',
 'checkout_409_key_reused.json':'CheckoutConflictError',
 'receipt_200_confirmed.json':'ReceiptRead',
 'checkout_request.json':'CheckoutRequest',
 'checkout_409_price_changed.json':'PriceChangedError',
 'receipt_confirm_request.json':'ReceiptVersionRequest',
 'ai_answer_200.json':'AIAskResponse',
 'low_stock_200.json':'LowStockPage',
 'inventory_adjust_noop_200.json':'AdjustResponse',
 'reapply_request_202.json':'GenericMessage',
 'forgot_password_202.json':'GenericMessage',
 'checkout_201.json':'OrderRead',
 'approval_pending_200.json':'ApprovalPage',
 'receipt_409_stale.json':'ErrorResponse',
}
fixtures=list((ROOT/'contracts/examples').glob('*.json'))
assert len(fixtures)==18, len(fixtures)
for f in fixtures:
    content=json.loads(f.read_text(encoding='utf-8'))
    if f.name in fixture_mapping:
        failures=list(validator(fixture_mapping[f.name]).iter_errors(content))
        assert not failures,(f.name,[(list(x.path),x.message) for x in failures[:4]])
    elif f.name=='ai_get_top_products_args.json':
        pass # validated below against machine-readable tool schema
    elif f.name=='outbox_broker_event.json':
        assert {'event_id','schema_version'}<=content.keys()
    else:raise AssertionError(f'Chưa mapping fixture {f.name}')

ai=json.loads((ROOT/'contracts/ai_tool_schemas.json').read_text(encoding='utf-8'))
expected={'get_sales_summary','get_top_products','get_slow_products','get_low_stock'}
assert set(ai['tools'])==expected
for name,record in ai['tools'].items():
    for key in ['input','output']:
        schema=record[key]
        assert schema.get('additionalProperties') is False
        Draft7Validator.check_schema(schema)
    assert 'actor_id' not in record['input']['properties']
    assert 'role' not in record['input']['properties']
    assert 'sql' not in record['input']['properties']
args=json.loads((ROOT/'contracts/examples/ai_get_top_products_args.json').read_text(encoding='utf-8'))
assert not list(Draft7Validator(ai['tools']['get_top_products']['input']).iter_errors(args))
# Hostile input is rejected, even if model tries to impersonate admin.
for payload in [{**args,'actor_id':1},{**args,'role':'ADMIN'},{**args,'sql':'SELECT * FROM users'}]:
    assert list(Draft7Validator(ai['tools']['get_top_products']['input']).iter_errors(payload))

# Source-of-truth: 57 LMS graph records, no hard cycle, task headings, owners and names match.
graph=json.loads((ROOT/'contracts/task_dependencies.json').read_text(encoding='utf-8'))
tasks=graph['tasks'];ids=[t['lms_id'] for t in tasks]
assert len(tasks)==57 and len(set(ids))==57
byid={x['lms_id']:x for x in tasks}
indegree={x:0 for x in ids};nexts=defaultdict(list)
for t in tasks:
    assert set(t['integrate_after'])<=set(ids),t['lms_id']
    for dep in t['integrate_after']:
        assert dep!=t['lms_id']
        indegree[t['lms_id']]+=1
        nexts[dep].append(t['lms_id'])
ready=deque(k for k,n in indegree.items() if n==0);count=0
while ready:
    v=ready.popleft();count+=1
    for target in nexts[v]:
        indegree[target]-=1
        if indegree[target]==0:ready.append(target)
assert count==57, f'Cyclic graph, processed only {count}/57'
for sprint,expected in [(2,26),(3,31)]:
    body=(DOCS/f'sprint{sprint}/TASK_IMPLEMENTATION_GUIDE.md').read_text(encoding='utf-8')
    headings=re.findall(r'^## (T04[A-Z0-9]+) — ([^\n]+)',body,re.M)
    assert len(headings)==expected,(sprint,len(headings))
    for task_id,title in headings:
        assert task_id in byid,(sprint,task_id)
        entry=byid[task_id]
        assert entry['sprint']==sprint,(task_id,entry['sprint'],sprint)
        assert entry['title']==title,(task_id,title,entry['title'])
        assert body.count(f'**Cổng dependency cho `{task_id}`')==1
        section=body.split(f'## {task_id} — ')[1].split('\n## ',1)[0]
        assert f'**Người phụ trách:** {entry["owner"]}' in section,task_id
        assert '**STARTABLE:**' in section and '**INTEGRATABLE:**' in section and '**ACCEPTED:**' in section

start=(DOCS/'START_HERE.md').read_text(encoding='utf-8')
for taskid in ids:assert f'| `{taskid}` |' in start,taskid
assert len(re.findall(r'^\| `T04[A-Z0-9]+` \|',start,re.M))==57

# LMS baseline được trích trực tiếp từ tab 1 của workbook do người dùng cung cấp.
# Không cần mang file XLSX trong repo; JSON snapshot có SHA-256 của workbook nguồn.
base_lms=json.loads((ROOT/'contracts/lms_task_baseline.json').read_text(encoding='utf-8'))
assert len(base_lms['tasks'])==57
bymap={x['lms_id']:x for x in base_lms['tasks']}
assert set(bymap)==set(ids)
for taskid,actual in byid.items():
    baseline=bymap[taskid]
    assert (actual['title'],actual['owner'],actual['sprint'])==(baseline['title'],baseline['owner'],baseline['sprint']), (taskid,baseline,actual)

# Chỉ số tham chiếu class.method trong docs phải tồn tại trong các .pyi chuẩn.
# Chỉ quét class có method để không nhầm enum/dataclass fields.
abi={}
for p in (ROOT/'contracts/python').glob('*.pyi'):
    tree=ast.parse(p.read_text(encoding='utf-8'))
    for cls in [n for n in tree.body if isinstance(n,ast.ClassDef)]:
        methods={n.name for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        if methods:abi[cls.name]=methods
for cls,methods in abi.items():
    for method in re.findall(r'\b'+re.escape(cls)+r'\.([A-Za-z_][A-Za-z0-9_]*)','\n'.join(f.read_text(encoding='utf-8') for f in DOCS.rglob('*.md'))):
        assert method in methods,(cls,method,'phương thức không có trong .pyi')

# No known stale/contradictory ABI names or file names.
contents='\n'.join(f.read_text(encoding='utf-8') for f in DOCS.rglob('*.md'))
for bad in ['CancelOrderService.cancel','OutboxPublisher.poll_publish',
            'AIToolExecutor.execute(tool_id,args,principal,session)',
            'S2_CORE_CONTRACTS_LOCKED.md','S2_REMAINING_CONTRACTS.md',
            'S2-xx','S3-xx','../shared/','workflow/DECISION_REGISTER.md','/products?q=']:
    assert bad not in contents,bad
for f in (ROOT/'contracts/python').glob('*.pyi'):ast.parse(f.read_text(encoding='utf-8'))
# Core+extended have canonical methods; no missing read ports.
code='\n'.join(f.read_text(encoding='utf-8') for f in (ROOT/'contracts/python').glob('*.pyi'))
for signature in ['class ReceiptReadService:', 'class OrderReadService:',
                  'class OutboxPublisher:', 'def publish_due(', 'class EmailEventHandler:',
                  'class AIToolExecutor:', 'class OrderService:', 'def cancel(']:assert signature in code,signature

# Dán đường dẫn trong Markdown phải chỉ tới file thật; external URLs/anchors ignored.
allmd=list(DOCS.rglob('*.md'))+[ROOT/'README.md',ROOT/'contracts/README.md']
for file in allmd:
    text=file.read_text(encoding='utf-8')
    for path in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',text):
        path=path.split('#')[0].strip()
        if not path or path.startswith(('https://','http://','mailto:')):continue
        if path.startswith('sandbox:'):continue
        assert (file.parent/path).exists(),(file.relative_to(ROOT),path)

print(f'CF-2.3 REVIEW GATE STATIC PASS: {len(ops)} HTTP, {len(schemas)} schemas, {len(fixtures)} fixtures validated, 4 AI tool schemas, 57 tasks, {sum(len(t["integrate_after"]) for t in tasks)} DAG edges, 0 cyclic dependencies.')
print('LIMIT: Product API matches pinned develop router snapshot; code/HTTP/MySQL/E2E tests MUST run separately before implementation acceptance.')
