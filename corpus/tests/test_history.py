import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))

import projection
import query
from history import append_projection_attempt


class NativeHistoryTests(unittest.TestCase):
    def setUp(self):
        ProjectionFixture = importlib.import_module("test_query_projection").CorpusTests
        self.fixture = ProjectionFixture("test_query_filters_pages_and_exact_row_lookup")
        self.fixture.setUp()
        self.addCleanup(self.fixture.temporary.cleanup)
        self.bundle = self.fixture.bundle
        self.row = query.select_rows(self.fixture.db, kind="benchmark", limit=1)["rows"][0]
        self.receipt = projection.reproject(self.bundle, self.row["row_id"], actor="QA operator \u2122")
        self.work = Path(tempfile.mkdtemp(prefix="cantos-native-history-"))
        self.addCleanup(lambda: shutil.rmtree(self.work, ignore_errors=True))
        self.packet = self.work / "source.research-packet.json"
        self.receipt_path = self.work / "receipt.json"
        self.receipt_path.write_text(json.dumps(self.receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._make_packet()

    def _make_packet(self):
        row_path = self.work / "row.json"
        row_path.write_text(json.dumps(self.row, ensure_ascii=False), encoding="utf-8")
        script = r"""
const fs=require('node:fs'),crypto=require('node:crypto');
const app=fs.readFileSync(process.argv[1],'utf8'), row=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const out=process.argv[3], expected='6375c45ae35890250020ae24e3edfc18a9c9e3bc7f2fa92dd87e578e1d29f0a5';
const m=[...app.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].find(x=>x[1].includes('root.ResearchCore=api'));
if(!m)throw Error('ResearchCore missing');
const core=Buffer.from(m[1]); if(crypto.createHash('sha256').update(core).digest('hex')!==expected)throw Error('ResearchCore pin mismatch');
const mod={exports:{}}; new Function('module','require',core.toString('utf8'))(mod,require);
(async()=>{const C=mod.exports,ws=C.empty('native history test fixture');
await C.put(ws,{id:'fixture-batch',kind:'source',title:'Fixture source observation',summary:'One retained synthetic fixture row; not a benchmark execution.',tier:'synthetic',disposition:'observed',deps:[],data:{rows:[row],row_count:1}},'Fixture importer \u2014 test only');
const packet=await C.pack(ws); await C.verifyPacket(packet); fs.writeFileSync(out,JSON.stringify(packet));})().catch(e=>{console.error(e);process.exitCode=1});
"""
        done = subprocess.run(
            ["node", "-e", script, str(REPO / "research-desk" / "app.html"), str(row_path), str(self.packet)],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(0, done.returncode, done.stderr)

    def test_append_replays_tamper_and_extends_reopened_unicode_packet(self):
        source_bytes = self.packet.read_bytes()
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        self.assertIn("\u2014".encode("utf-8"), source_bytes)

        forged = json.loads(json.dumps(self.receipt))
        forged["rebuilt"]["measurement"]["value"] += 1
        bad = self.work / "forged.json"
        bad.write_text(json.dumps(forged, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "deterministic replay at rebuilt"):
            append_projection_attempt(self.packet, bad, self.work / "forged-out", bundle=self.bundle)
        self.assertFalse((self.work / "forged-out").exists())

        with self.assertRaisesRegex(ValueError, "outside the retained bundle"):
            append_projection_attempt(self.packet, self.receipt_path, self.bundle / "native", bundle=self.bundle)

        first = append_projection_attempt(self.packet, self.receipt_path, self.work / "first", bundle=self.bundle)
        first_path = Path(first["packet_path"])
        first_packet = json.loads(first_path.read_bytes())
        self.assertEqual(first["native_packet_sha256"], first_packet["sha256"])
        source_record = next(e["payload"] for e in first_packet["workspace"]["events"]
                             if e.get("type") == "record" and e["payload"].get("id") == first["source_record_id"])
        self.assertEqual(self.receipt["bundle"], source_record["data"]["bundle"])
        self.assertIn("\u2014".encode("utf-8"), first_path.read_bytes())

        receipt2 = projection.reproject(self.bundle, self.row["row_id"], actor="QA operator \u2122")
        receipt2_path = self.work / "receipt2.json"
        receipt2_path.write_text(json.dumps(receipt2, ensure_ascii=False), encoding="utf-8")
        second = append_projection_attempt(first_path, receipt2_path, self.work / "second", bundle=self.bundle)
        second_packet = json.loads(Path(second["packet_path"]).read_bytes())

        self.assertEqual(len(first_packet["workspace"]["events"]) + 2, len(second_packet["workspace"]["events"]))
        self.assertEqual(first["source_record_id"], second["source_record_id"])
        self.assertNotEqual(first["claim_record_id"], second["claim_record_id"])
        self.assertEqual(2, second["source_record_revision"])
        self.assertEqual(1, second["claim_record_revision"])
        latest_claim = next(e["payload"] for e in reversed(second_packet["workspace"]["events"])
                            if e.get("type") == "record" and e["payload"].get("id") == second["claim_record_id"])
        self.assertIn({"id": second["source_record_id"], "revision": 2}, latest_claim["deps"])
        self.assertEqual(source_sha, hashlib.sha256(self.packet.read_bytes()).hexdigest())
        self.assertTrue(first["source_packet_preserved"])
        self.assertTrue(second["source_packet_preserved"])
        self.assertFalse(first["authenticated_actor"])
        self.assertFalse(second["authenticated_actor"])


if __name__ == "__main__":
    unittest.main()
