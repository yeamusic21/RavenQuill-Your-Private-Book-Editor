import time

from fastapi.testclient import TestClient


def wait_for_job(client, project_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/projects/{project_id}/job").json()
        if job and job["status"] in ("done", "error", "paused"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_full_run(app_env, sample_docx):
    with TestClient(app_env.app) as client:
        with open(sample_docx, "rb") as f:
            project = client.post("/api/projects", data={"name": "Test Book"},
                                  files={"file": ("book.docx", f)}).json()
        pid = project["id"]
        assert project["stats"]["paragraphs"] == 7

        client.post(f"/api/projects/{pid}/run", json={"stages": ["architect", "prose", "copyedit", "proofread"]})
        job = wait_for_job(client, pid)
        assert job["status"] == "done", job

        project = client.get(f"/api/projects/{pid}").json()
        assert project["report"] and project["voice_profile"]

        chapters = client.get(f"/api/projects/{pid}/chapters").json()
        pars = client.get(f"/api/chapters/{chapters[0]['id']}/paragraphs").json()
        rex = pars[1]
        assert rex["current"].startswith("There was a dog named Rex and he ran fast down the road.")
        assert "<i>Faster</i>" in rex["current"]
        assert "prose" in rex["edited_by"] and rex["diff"]
        assert pars[4]["current"] == "The next morning it was raining—hard. She waited…"  # typography

        # Author edits inline, then reverts.
        edited = client.patch(f"/api/paragraphs/{rex['id']}", json={"current": "Rex ran."}).json()
        assert edited["current"] == "Rex ran." and edited["reviewed"]
        reverted = client.post(f"/api/paragraphs/{rex['id']}/revert").json()
        assert reverted["current"] == rex["original"]

        for kind in ("edited", "tracked", "original", "report"):
            assert client.get(f"/api/projects/{pid}/export/{kind}").status_code == 200

        checkpoints = project["checkpoints"]
        assert {c["label"] for c in checkpoints} >= {"Original upload", "After prose"}
        original = next(c for c in checkpoints if c["label"] == "Original upload")
        client.post(f"/api/projects/{pid}/checkpoints/{original['id']}/restore")
        pars = client.get(f"/api/chapters/{chapters[0]['id']}/paragraphs").json()
        assert all(not p["changed"] for p in pars)
