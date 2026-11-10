import ast
import io
from pathlib import Path
import unittest
import urllib.error
from unittest import mock

class InstagramRateLimitTests(unittest.TestCase):
    def setUp(self):
        source=Path("bot.py").read_text()
        tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="parse_instagram_sale_items")
        self.refresh=mock.Mock()
        self.ns={"refresh_instagram_catalog":self.refresh,"urllib":urllib,
            "books":[{"id":1,"name":"Yusufning qizi","stock":5}],
            "_instagram_name_key":lambda value:str(value).lower().strip(),
            "_instagram_qty_token":lambda value:int(value) if str(value).isdigit() else None,
            "_instagram_fuzzy_matches":lambda value:[],
            "print":mock.Mock()}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"bot.py","exec"),self.ns)
    def set_failure(self,code):
        try:
            raise urllib.error.HTTPError("https://gateway.test",code,"temporary",{},io.BytesIO(b"rate limited"))
        except urllib.error.HTTPError as cause:
            error=RuntimeError("gateway temporarily unavailable")
            error.__cause__=cause
            self.refresh.side_effect=error
    def test_temporary_429_keeps_name_entry_working_without_writing_stock(self):
        self.set_failure(429)
        self.assertEqual(self.ns["parse_instagram_sale_items"]("Yusufning qizi 1"),({"1":1},[]))
        self.assertEqual(self.ns["books"][0]["stock"],5)
    def test_missing_cache_or_authentication_error_never_falls_back(self):
        self.set_failure(429);self.ns["books"]=[]
        with self.assertRaises(RuntimeError):self.ns["parse_instagram_sale_items"]("Yusufning qizi 1")
        self.ns["books"]=[{"id":1,"name":"Yusufning qizi","stock":5}];self.set_failure(401)
        with self.assertRaises(RuntimeError):self.ns["parse_instagram_sale_items"]("Yusufning qizi 1")
    def test_success_still_refreshes_catalog_before_matching(self):
        self.assertEqual(self.ns["parse_instagram_sale_items"]("Yusufning qizi 1"),({"1":1},[]))
        self.refresh.assert_called_once_with()

if __name__=="__main__":unittest.main()
