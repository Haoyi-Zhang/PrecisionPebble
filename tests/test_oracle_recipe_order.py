"""Current oracle agrees with every retained oracle result and bounded gates."""
import builtins
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src import oracle
from src.model import load_instance
from src.event_checker import check_events

def scientific(result):
    value=result.to_json();value.pop('cpu_seconds')
    return value

def records():
    return json.loads((ROOT/'instances/index.json').read_text(encoding='utf-8'))['records']

class OracleRecipeOrderTests(unittest.TestCase):
    def test_every_retained_oracle_result_and_witness(self):
        count=0
        for record in records():
            if not record['oracle']:
                continue
            instance=load_instance(ROOT/'instances'/record['file'])
            stored=json.loads((ROOT/'results/evaluation/cases'/Path(record['file']).name).read_text(encoding='utf-8'))['oracle']
            with patch.object(oracle.time,'process_time',return_value=0):
                result=oracle.configuration_oracle(instance,state_cap=50000,cpu_cap=15)
            expected={k:v for k,v in stored.items() if k!='cpu_seconds'}
            self.assertEqual(scientific(result),expected,record['name'])
            if result.cost is not None:
                replay=check_events(instance,result.events)
                self.assertTrue(replay.valid,replay.error)
                self.assertEqual(replay.cost,result.cost)
            count+=1
        self.assertEqual(count,286)

    def test_call_local_one_build_and_recipe_order(self):
        path=ROOT/'instances/campaign/285-hardness-no-scaled.json'
        outputs=[]
        for reverse in (False,True,False):
            instance=load_instance(path)
            if reverse:
                instance=replace(instance,nodes={key:replace(node,recipes=tuple(reversed(node.recipes))) for key,node in instance.nodes.items()})
            lookup={id(node.recipes):key for key,node in instance.nodes.items() if node.kind=='op'}
            builds=Counter()
            def counted(values,**kwargs):
                if 'key' in kwargs:
                    builds[lookup[id(values)]]+=1
                return builtins.sorted(values,**kwargs)
            with patch.object(oracle,'sorted',counted,create=True),patch.object(oracle.time,'process_time',return_value=0):
                result=oracle.configuration_oracle(instance,state_cap=50000,cpu_cap=15)
            self.assertTrue(builds)
            self.assertTrue(all(n==1 for n in builds.values()))
            outputs.append(scientific(result))
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])

    def test_state_and_cpu_caps_remain_fail_closed(self):
        for record in [r for r in records() if r['group'] in ('control','hardness')]:
            instance=load_instance(ROOT/'instances'/record['file'])
            for cap in (1,2):
                with patch.object(oracle.time,'process_time',return_value=0):
                    result=oracle.configuration_oracle(instance,state_cap=cap,cpu_cap=15)
                self.assertEqual(result.status,'state_cap')
                self.assertIsNone(result.cost);self.assertEqual(result.events,[])
            observed=[0]
            def clock():
                observed[0]+=1
                return 0 if observed[0]<=5 else 16
            with patch.object(oracle.time,'process_time',side_effect=clock):
                result=oracle.configuration_oracle(instance,state_cap=50000,cpu_cap=15)
            if record['name']=='hardness-no-scaled':
                self.assertEqual(result.status,'cpu_cap')
                self.assertEqual(observed[0],7)
            if result.status=='cpu_cap':
                self.assertIsNone(result.cost);self.assertEqual(result.events,[])
            else:
                self.assertEqual(result.status,'complete')

if __name__=='__main__':
    unittest.main()
