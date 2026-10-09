import csv

import testrunner as tr


def run(steps, lines_at):
    sent = []
    r = tr.Runner(steps, lambda s: sent.append(s) or True, now=0.0)
    t = 0.0
    while not r.done and t < 60:
        t = round(t + 0.1, 1)
        for line in lines_at.get(t, []):
            r.feed_line(line, now=t)
        r.tick(now=t)
    return r, sent


def test_pass_fail_timeout_regex_continue():
    steps = [tr.make_step("mfg get_version", "v1.", 2),
             tr.make_step("led red", r"re:led\s+ok", 2, on_fail="continue"),
             tr.make_step("audio", "PASS", 1),
             tr.make_step("", "", 0.5)]
    r, sent = run(steps, {0.3: ["boot", "version v1.2.3"], 0.5: ["led FAIL"], 2.8: ["audio PASS"]})
    assert sent == ["mfg get_version", "led red", "audio"]
    assert [x["status"] for x in r.results] == ["PASS", "FAIL", "PASS", "PASS"]
    assert r.summary() == {"total": 4, "passed": 3, "failed": 1, "result": "FAIL"}


def test_stop_on_fail_and_csv(tmp_path):
    steps = [tr.make_step("a", "OK", 1), tr.make_step("b", "OK", 1)]
    r, sent = run(steps, {})
    assert sent == ["a"] and r.results[0]["status"] == "FAIL" and r.done
    p = tmp_path / "out" / "results.csv"
    tr.append_csv(str(p), "seq", "SN123", r, "Serial COM7")
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    assert rows[0][0] == "time" and rows[1][2] == "SN123" and rows[1][8] == "FAIL"


def test_all_pass():
    r, _ = run([tr.make_step("x", "OK", 1)], {0.2: ["all OK"]})
    assert r.passed and r.summary()["result"] == "PASS"


def test_store(tmp_path):
    s = tr.SequenceStore(str(tmp_path / "seq.json"))
    s.put(0, {"name": "Boot", "steps": [tr.make_step("x", "OK", 3)]})
    s2 = tr.SequenceStore(str(tmp_path / "seq.json"))
    assert s2.names() == ["Boot"] and s2.get(0)["steps"][0]["timeout"] == 3.0
