"""EXTERNAL_TEST mode end to end on a tiny synthetic corpus (mechanics only, no scientific content).

Copies this project to a temp folder, builds 3 synthetic PDFs + a registry + a TRAIN_DEV identity list, then
runs bootstrap (propose/finalize) -> init -> import-xlsx -> seed (must be blocked) -> preflight -> seed ->
SCOPE/TEMPORAL submissions and checks the TEST gates."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cwd, *args):
    r = subprocess.run([PY, "-X", "utf8", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def make_pdf(path, lines):
    import fitz
    d = fitz.open()
    p = d.new_page()
    y = 72
    for t in lines:
        p.insert_text((72, y), t, fontsize=11)
        y += 18
    d.save(path)


class TestExternalTestMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="tt_"))
        proj = cls.tmp / "p"
        proj.mkdir()
        for name in ["CLAUDE.md", "config", "tools", "schema", ".claude", "docs", "requirements.txt"]:
            src = ROOT / name
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, proj / name)
        for d in ["db", "manifests", "work", "inputs"]:
            (proj / d).mkdir(exist_ok=True)
        (proj / ".claude" / "settings.local.json").unlink(missing_ok=True)
        papers = cls.tmp / "papers"
        papers.mkdir()
        make_pdf(papers / "a.pdf", ["https://doi.org/10.9999/test.0001", "Seaweed extract improves tomato yield under drought",
                                     "Published online: 5 March 2024"])
        make_pdf(papers / "b.pdf", ["https://doi.org/10.9999/test.0002", "Chitosan protects tomato under salinity",
                                     "Published online: 1 July 2023"])
        make_pdf(papers / "c.pdf", ["https://doi.org/10.9999/train.0001", "A paper already used for training"])
        import pandas as pd
        reg = pd.DataFrame([
            {"№": 1, "Год онлайн / издания": "2024", "Тип стресса": "a", "Стресс-фактор": "drought", "Биостимулятор / агент": "x",
             "Точное название статьи (EN)": "Seaweed extract improves tomato yield under drought", "DOI": "10.9999/test.0001",
             "Соответствие": "Прямое", "Пояснение / ограничения": "", "Ссылка на источник": ""},
            {"№": 2, "Год онлайн / издания": "2024", "Тип стресса": "a", "Стресс-фактор": "salt", "Биостимулятор / агент": "y",
             "Точное название статьи (EN)": "Chitosan protects tomato under salinity", "DOI": "10.9999/test.0002",
             "Соответствие": "Прямое", "Пояснение / ограничения": "", "Ссылка на источник": ""},
            {"№": 3, "Год онлайн / издания": "2024", "Тип стресса": "a", "Стресс-фактор": "salt", "Биостимулятор / агент": "z",
             "Точное название статьи (EN)": "A paper already used for training", "DOI": "10.9999/train.0001",
             "Соответствие": "Прямое", "Пояснение / ограничения": "", "Ссылка на источник": ""},
            {"№": 4, "Год онлайн / издания": "2025", "Тип стресса": "a", "Стресс-фактор": "heat", "Биостимулятор / агент": "w",
             "Точное название статьи (EN)": "No full text for this one", "DOI": "10.9999/test.0004",
             "Соответствие": "Прямое", "Пояснение / ограничения": "", "Ссылка на источник": ""}])
        reg.to_excel(papers / "tomato_biostimulants_stress_2024_2026_registry.xlsx", index=False)
        freeze = cls.tmp / "a399"
        freeze.mkdir()
        pd.DataFrame([{"study_id": "1", "doi": "10.9999/train.0001", "title": "A paper already used for training",
                       "year": 2023}]).to_csv(freeze / "db_studies.csv", index=False)
        cls.lock = cls.tmp / "MODEL_FREEZE.json"
        cls.lock.write_text(json.dumps({"freeze_at_utc": "2026-01-01T00:00:00+00:00"}))
        cls.proj, cls.papers, cls.freeze = proj, papers, freeze

    @classmethod
    def tearDownClass(cls):
        for p in (cls.tmp / "corpus").rglob("*"):
            if p.is_file():
                p.chmod(0o666)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_end_to_end(self):
        p, common = self.proj, ["--papers", str(self.papers), "--train-dev-freeze", str(self.freeze)]
        code, out = run(p, "tools/bootstrap_test_corpus.py", *common)
        self.assertEqual(code, 0, out)
        code, out = run(p, "tools/bootstrap_test_corpus.py", *common, "--finalize", "--corpus", str(self.tmp / "corpus"),
                        "--model-freeze", str(self.lock))
        self.assertEqual(code, 0, out)  # all rows AUTO-approved
        res = json.loads(out[out.index("{"):])
        self.assertEqual(res["scope_studies"], 2)  # T001, T002 (T003 = TRAIN_DEV overlap, T004 = no full text)
        self.assertEqual(res["excluded_by_reason"], {"NO_FULLTEXT": 1, "TRAIN_DEV_OVERLAP": 1})
        for cmd in (["init"], ["import-xlsx"]):
            code, out = run(p, "tools/tfm.py", *cmd)
            self.assertEqual(code, 0, out)
        code, out = run(p, "tools/tfm.py", "seed")
        self.assertIn("MODEL_FREEZE not recorded", out)
        code, out = run(p, "tools/tfm.py", "preflight")
        self.assertEqual(json.loads(out)["status"], "PASS", out)
        run(p, "tools/tfm.py", "metadata-normalize")
        code, out = run(p, "tools/tfm.py", "seed")
        self.assertEqual(code, 0, out)
        code, out = run(p, "tools/tfm.py", "claim", "--limit", "4", "--owner", "t", "--types", "SCOPE,TEMPORAL")
        tasks = {(t["study_id"], t["task_type"]): t["task_id"] for t in json.loads(out)["tasks"]}
        self.assertEqual(len(tasks), 4)
        src = {}
        for sid in ("T001", "T002"):
            code, out = run(p, "tools/tfm.py", "sql", f"SELECT source_file_id FROM wf_sources WHERE study_id='{sid}'")
            fid = json.loads(out)[0]["source_file_id"]
            code, out = run(p, "tools/tfm.py", "source-view", fid, "--page", "1")
            src[sid] = (fid, json.loads(out)["receipt_id"])
        outbox = p / "work" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)

        def submit(tid, payload):
            f = outbox / f"{tid}.json"
            f.write_text(json.dumps(payload))
            return run(p, "tools/tfm.py", "submit", tid, str(f))

        base = {"agent": "tfm-scope-auditor", "model_id": "TEST"}
        t = tasks[("T001", "TEMPORAL")]
        code, out = submit(t, {**base, "task_id": t, "study_id": "T001", "eligibility": "ELIGIBLE_TEST_WINDOW",
                               "source_file_id": src["T001"][0], "receipt_id": src["T001"][1],
                               "first_online_date": "2024-03-05", "evidence": "Published online: 5 March 2024"})
        self.assertEqual(code, 0, out)
        t = tasks[("T001", "SCOPE")]
        code, out = submit(t, {**base, "task_id": t, "study_id": "T001", "notes": None, "proposed_class": "A",
                               "reason": "tomato, drought, seaweed extract, primary experiment",
                               "evidence": [{"locator": "p1", "quote": "Seaweed extract"}], "confidence": "HIGH"})
        self.assertEqual(code, 0, out)
        self.assertIn("TRIAGE:", out)
        t = tasks[("T002", "TEMPORAL")]
        code, out = submit(t, {**base, "task_id": t, "study_id": "T002", "eligibility": "INELIGIBLE_PRE2024",
                               "source_file_id": src["T002"][0], "receipt_id": src["T002"][1],
                               "first_online_date": "2023-07-01", "evidence": "Published online: 1 July 2023"})
        self.assertEqual(code, 0, out)
        code, out = run(p, "tools/tfm.py", "sql", "SELECT study_id,state FROM wf_study_status ORDER BY study_id")
        self.assertEqual({r["study_id"]: r["state"] for r in json.loads(out)}, {"T001": "NEW", "T002": "EXCLUDED_SCOPE"})
        code, out = run(p, "tools/tfm.py", "gates")
        g = {x["gate"]: x["status"] for x in json.loads(out).get("gates", json.loads(out))}
        for gate in ("dataset_role_external_test", "temporal_window_source_verified", "no_overlap_with_train_dev",
                     "model_frozen_before_test_extraction", "frozen_scope"):
            self.assertEqual(g[gate], "PASS", (gate, out[-2000:]))

    def test_blinding_hook_blocks_ml_package(self):
        hook = ROOT / ".claude" / "hooks" / "guard_tool.py"
        payload = json.dumps({"tool_name": "Read", "tool_input": {
            "file_path": "C:/Users/x/Desktop/SynerPlant_Local_ML_Starter/SynerPlant_Local_ML/outputs/yield/cv_predictions.csv"}})
        r = subprocess.run([PY, str(hook)], input=payload, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
