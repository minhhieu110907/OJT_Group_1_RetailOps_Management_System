"""Static doc contract verification; requires PyYAML, no database/network."""
import ast
import json
from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]
spec=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text(encoding='utf-8'))
assert spec['openapi'].startswith('3.0.'), 'OpenAPI 3.0 expected'
assert spec['servers'][0]['url']=='/api/v1'
schemas=spec['components']['schemas']
ops={ (p,m):v for p,verbs in spec['paths'].items() for m,v in verbs.items() if m in ('get','post','put','patch','delete') }
assert len(ops)>=26, len(ops)
for (path,method),op in ops.items():
 for ref in re.findall(r"#/components/schemas/([A-Za-z0-9_]+)",str(op)):
  assert ref in schemas, (path,method,ref)
for schema in schemas.values():
 for ref in re.findall(r"#/components/schemas/([A-Za-z0-9_]+)",str(schema)):
  assert ref in schemas,ref
need=[('/orders/checkout','post'),('/orders/{order_id}/cancel','post'),('/purchase-receipts/{receipt_id}/confirm','post'),('/inventory/{product_id}/adjustments','post')]
for key in need:
 op=ops[key]
 assert op['x-contract-status']=='FROZEN_DESIGN'
 assert op.get('x-idempotency',{}).get('single_mysql_transaction') is True
 assert any(p.get('name')=='Idempotency-Key' and p.get('required') for p in op.get('parameters',[])),key
for p in (ROOT/'contracts/examples').glob('*.json'):
 json.loads(p.read_text(encoding='utf-8'))
ast.parse((ROOT/'contracts/python/retailops_core_ports.pyi').read_text(encoding='utf-8'))
for folder,expected in [('sprint2',26),('sprint3',31)]:
 t=(ROOT/f'docs/{folder}/TASK_IMPLEMENTATION_GUIDE.md').read_text(encoding='utf-8')
 count=len(re.findall(r'^## T04[A-F0-9]+ — ',t,re.M))
 assert count==expected,(folder,count)
print(f'OK: {len(ops)} HTTP operations, {len(schemas)} schemas, 57 task cards, Python stubs and JSON fixtures parsed.')
