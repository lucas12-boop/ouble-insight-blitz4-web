"""Offline contract tests only; no access to Blitz4, secrets or production server."""
import unittest
from datetime import datetime, timezone
from blitz4_collector import parse_rounds
class CollectorValidation(unittest.TestCase):
    def test_rejects_other_game(self):
        with self.assertRaises(ValueError):
            parse_rounds({'game':'blaze-double','rounds':[{'id':'1','number':0,'created_at':datetime.now(timezone.utc).isoformat()}]})
    def test_rejects_undocumented_payload(self):
        with self.assertRaises(ValueError):
            parse_rounds({'results':[]})
    def test_maps_whites_and_colors(self):
        now=datetime.now(timezone.utc).isoformat()
        res=parse_rounds({'game':'blitz4-double','rounds':[{'id':'a','number':0,'created_at':now},{'id':'b','number':7,'created_at':now},{'id':'c','number':14,'created_at':now}]})
        self.assertEqual([x['color'] for x in res],['branco','amarelo','escuro'])
    def test_drops_invalid_numbers(self):
        now=datetime.now(timezone.utc).isoformat()
        res=parse_rounds({'game':'blitz4-double','rounds':[{'id':'a','number':15,'created_at':now},{'id':'b','number':False,'created_at':now}]})
        self.assertFalse(res)
if __name__=='__main__':unittest.main()
