"""Kiểm tra tĩnh nhanh, không dùng mạng/database; không chứng minh runtime test PASS."""
import ast,json,re,yaml
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=yaml.safe_load((R/'contracts/openapi.yaml').read_text(encoding='utf-8'))
assert s['openapi'].startswith('3.0.'), 'OpenAPI 3.0 required'
assert s['servers'][0]['url']=='/api/v1'
ops={ (p,m):o for p,vs in s['paths'].items() for m,o in vs.items() if m in ('get','post','patch','put','delete') }
assert len(ops)>=29, len(ops)
ids=[o['operationId'] for o in ops.values()]
assert len(ids)==len(set(ids)), 'duplicate operationId'
schemas=s['components']['schemas']
for k in ops:
 op=ops[k]
 assert op.get('x-contract-status') and op.get('x-implementation-status')
 for schema_ref in re.findall(r"#/components/schemas/([\w]+)",str(op)):
  assert schema_ref in schemas,(k,schema_ref)
for name,sch in schemas.items():
 for ref in re.findall(r"#/components/schemas/([\w]+)",str(sch)):
  assert ref in schemas,(name,ref)
 if 'required' in sch:assert set(sch['required']).issubset(sch.get('properties',{})),name
for f in (R/'contracts/python').glob('*.pyi'):ast.parse(f.read_text(encoding='utf-8'))
fixtures=list((R/'contracts/examples').glob('*.json'))
for f in fixtures:json.loads(f.read_text(encoding='utf-8'))
for sprint,expected in [(2,26),(3,31)]:
 t=(R/f'docs/sprint{sprint}/TASK_IMPLEMENTATION_GUIDE.md').read_text(encoding='utf-8')
 assert len(re.findall(r'^## T[A-Z0-9]+ — ',t,re.M))==expected
idx=(R/'docs/contracts/API_INTEGRATION.md').read_text(encoding='utf-8')
assert len(re.findall(r'^\| \[T[A-Z0-9]+ — ',idx,re.M))==57
for method,path in [('post','/orders/checkout'),('post','/orders/{order_id}/cancel'),('post','/purchase-receipts/{receipt_id}/confirm'),('post','/inventory/{product_id}/adjustments')]:
 o=ops[path,method]
 assert any(p['name']=='Idempotency-Key' and p['required'] for p in o.get('parameters',[])),(path,'missing key')
 assert o['x-idempotency']['single_mysql_transaction'] is True
print('CF2 STATIC PASS:',len(ops),'operations,',len(schemas),'schemas,',len(fixtures),'JSON fixtures, two typed Python files, 57 cards.')
