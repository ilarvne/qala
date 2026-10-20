"""Independent editorial-media checks. All provider responses are local fixtures."""
import copy
import hashlib
import io
import json

import httpx
import pytest
from PIL import Image

from scripts import collect_curated_commons as curated
from scripts.collect_pois import transform


ACQUIRED = "2024-02-03T04:05:06+06:00"
TITLE = "File:Saken Museum Astana.jpg"
DESCRIPTION = "Saken Seifullin Museum, Astana, Kazakhstan."


def dataset(count=1):
    result = transform({"elements": [{"type": "node", "id": index + 1, "lat": 51.1 + index * .0001, "lon": 71.4,
        "tags": {"name": f"Named Museum {index + 1}", "tourism": "museum", "opening_hours": "Tu-Su 10:00-18:00"}}
        for index in range(count)]}, "fixture", ACQUIRED)
    result["pois"][0].update(operating_status="closed", recommendable=False)
    return result


def seeds(data=None, files=1):
    data = data or dataset()
    return [{"poi_id": poi["id"], "target_fingerprint": curated.target_fingerprint(poi), "files": [
        {"title": TITLE if len(data["pois"]) == 1 and index == 0 else f"File:Named Museum {poi['id']} View {index}.jpg",
         "identity": {"method": "editorially_reviewed_named_venue", "local_source_url": poi["source"]["url"],
            "local_name": poi["name"], "source_description": DESCRIPTION, "reviewed_at": ACQUIRED,
            "review_note": "Manually reviewed the named physical venue and the source file description."}}
        for index in range(files)]} for poi in data["pois"]]


def page():
    return {"pageid": 123, "ns": 6, "title": TITLE, "categories": [{"title": "Category:Museums in Astana"}],
        "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Saken_Museum_Astana.jpg",
            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Saken_Museum_Astana.jpg/1000px-Saken_Museum_Astana.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Saken_Museum_Astana.jpg",
            "mime": "image/jpeg", "width": 1600, "height": 1000,
            "extmetadata": {"Artist": {"value": '<a href="https://commons.wikimedia.org/wiki/User:Photographer">Photographer</a>'},
                "AttributionRequired": {"value": "true"}, "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                "ImageDescription": {"value": "<div>" + DESCRIPTION + "</div>"},
                "NonFree": {"value": "false"}}}]}


def capture_response(source_page=None):
    return {"query": {"pages": {"123": source_page or page()}}}


def write_capture(folder, *, source_page=None, stamp=ACQUIRED):
    folder.mkdir(parents=True, exist_ok=True)
    body = capture_response(source_page)
    path = folder / "commons-fixture.json"
    capture = {"source_url": curated.API_URL, "requested_titles": [TITLE], "observed_at": stamp,
               "http_status": 200, "response_sha256": curated.digest(body), "response": body}
    path.write_text(json.dumps(capture))
    return path


def compile_fixture(tmp_path, *, data=None, source_page=None):
    data = data or dataset()
    write_capture(tmp_path / "source", source_page=source_page)
    return curated.compile_sidecar(data, seeds(data), curated.load_captures(tmp_path / "source"))


def png_bytes(size=(200, 180), color="navy"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def test_compile_requires_reviewed_description_and_retains_original_source_provenance(tmp_path):
    sidecar = compile_fixture(tmp_path)
    assert sidecar["held"] == [] and len(sidecar["assignments"]) == 1
    assignment = sidecar["assignments"][0]
    assert assignment["photo"]["observed_at"] == ACQUIRED
    assert assignment["photo"]["author"] == "Photographer"
    assert assignment["photo"]["license"] == "CC BY-SA 4.0"
    assert assignment["source_description_sha256"] == hashlib.sha256(DESCRIPTION.encode()).hexdigest()
    assert assignment["source_metadata"]["observed_at"] == ACQUIRED
    assert assignment["identity"]["method"] == "editorially_reviewed_named_venue"


def test_reviewed_cover_replaces_unhelpful_cover_without_losing_its_gallery_or_attribution(tmp_path):
    data = dataset()
    old = {"source_url": "https://commons.wikimedia.org/wiki/File:Old_panorama.jpg", "url": "/photos/old.jpg", "author": "Old author"}
    data["pois"][0].update(photos=[old], image=old["url"])
    selected = seeds(data)
    selected[0]["files"][0]["preferred_cover"] = True
    write_capture(tmp_path / "source")
    sidecar = curated.compile_sidecar(data, selected, curated.load_captures(tmp_path / "source"))
    result = curated.apply_curated_commons(data, sidecar)
    poi = result["pois"][0]
    assert poi["photos"][0]["source_url"] == page()["imageinfo"][0]["descriptionurl"]
    assert poi["photos"][0]["author"] == "Photographer"
    assert poi["photos"][1] == old
    assert poi["image"] == poi["photos"][0]["url"]
    assert poi["operating_status"] == "closed" and poi["recommendable"] is False
    assert data["pois"][0]["photos"] == [old]


def test_failed_republication_cannot_overwrite_active_raw_proof_or_its_normalized_snapshot(tmp_path):
    from scripts.publish_curated_expansion import SOURCE_PATH, publish
    project = tmp_path / "project"
    active = project / SOURCE_PATH
    active.mkdir(parents=True)
    (active / "source.json").write_text('{"original":true}')
    normalized = project / "data/pois.json"
    normalized.write_text(json.dumps({"metadata": {"curated_media_expansion": {"source_path": SOURCE_PATH}}, "pois": []}))
    before = normalized.read_bytes()
    stage = tmp_path / "stage"
    (stage / "raw").mkdir(parents=True)
    (stage / "raw/source.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="evidence is immutable"):
        publish(stage, project)
    assert (active / "source.json").read_text() == '{"original":true}'
    assert normalized.read_bytes() == before
    assert not (project / "public/photos").exists()


@pytest.mark.parametrize("problem", ["name", "coordinate", "source", "anonymous"])
def test_changed_or_anonymous_local_target_is_rejected_before_compilation(tmp_path, problem):
    data = dataset(); reviewed = seeds(data)
    if problem == "name": data["pois"][0]["name"] = "Different museum"
    elif problem == "coordinate": data["pois"][0]["lat"] += .01
    elif problem == "source": data["pois"][0]["source"]["url"] += "0"
    elif problem == "anonymous": data["pois"][0]["name_derived"] = True
    with pytest.raises(ValueError):
        curated.compile_sidecar(data, reviewed, {})


@pytest.mark.parametrize("problem", ["wrong_description", "no_license", "no_fop", "noncommercial", "no_derivatives", "foreign_license_url", "restrictions_warning"])
def test_unproven_identity_or_reuse_rights_are_held_out(tmp_path, problem):
    source_page = page(); meta = source_page["imageinfo"][0]["extmetadata"]
    if problem == "wrong_description": meta["ImageDescription"]["value"] = "A different building in a different city."
    elif problem == "no_license": meta.pop("LicenseShortName")
    elif problem == "no_fop": source_page["categories"].append({"title": "Category:NoFoP-Kazakhstan"})
    elif problem == "noncommercial":
        meta["LicenseShortName"]["value"] = "CC BY-NC 4.0"
        meta["LicenseUrl"]["value"] = "https://creativecommons.org/licenses/by-nc/4.0/"
    elif problem == "no_derivatives":
        meta["LicenseShortName"]["value"] = "CC BY-ND 4.0"
        meta["LicenseUrl"]["value"] = "https://creativecommons.org/licenses/by-nd/4.0/"
    elif problem == "foreign_license_url": meta["LicenseUrl"]["value"] = "https://creativecommons.org.evil.example/licenses/by-sa/4.0/"
    elif problem == "restrictions_warning": meta["Restrictions"] = {"value": "Copyright warning; deletion pending"}
    result = compile_fixture(tmp_path, source_page=source_page)
    assert result["assignments"] == [] and len(result["held"]) == 1


def test_forged_retained_metadata_hash_cannot_compile(tmp_path):
    folder = tmp_path / "source"; path = write_capture(folder)
    capture = json.loads(path.read_text())
    capture["response"]["query"]["pages"]["123"]["imageinfo"][0]["extmetadata"]["ImageDescription"]["value"] = "Changed source content"
    path.write_text(json.dumps(capture))
    with pytest.raises(ValueError, match="Invalid retained"):
        curated.load_captures(folder)


def test_metadata_http_denial_stops_campaign_and_next_invocation_before_any_request(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429)
    data = dataset(21)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="http_429"):
            curated.collect_metadata(seeds(data), tmp_path, client=client)
        assert len(calls) == 1
        stop = json.loads((tmp_path / "acquisition-stop.json").read_text())
        assert stop["http_status"] == 429
        with pytest.raises(ValueError, match="Previous acquisition stopped"):
            curated.collect_metadata(seeds(data), tmp_path, client=client)
        assert len(calls) == 1


def test_resumed_metadata_keeps_original_acquisition_time_without_transport(tmp_path):
    batch = [TITLE]
    filename = "commons-" + curated.digest(batch)[:16] + ".json"
    path = write_capture(tmp_path)
    path.rename(tmp_path / filename)
    original = (tmp_path / filename).read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("A replay must never refresh the original acquisition time"))) as client:
        result = curated.collect_metadata(seeds(), tmp_path, client=client)
    assert result["captures"] == [filename]
    assert (tmp_path / filename).read_bytes() == original
    assert curated.load_captures(tmp_path)[TITLE][1]["observed_at"] == ACQUIRED


@pytest.mark.parametrize("problem", ["source_url", "http_status"])
def test_resume_rejects_retained_capture_with_foreign_source_or_failed_status(tmp_path, problem):
    path = write_capture(tmp_path)
    capture = json.loads(path.read_text())
    capture[problem] = "https://foreign.example/api.php" if problem == "source_url" else 403
    path.write_text(json.dumps(capture))
    filename = "commons-" + curated.digest([TITLE])[:16] + ".json"
    path.rename(tmp_path / filename)
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Invalid saved captures cannot trigger new provider requests"))) as client:
        with pytest.raises(ValueError):
            curated.collect_metadata(seeds(), tmp_path, client=client)
    with pytest.raises(ValueError):
        curated.load_captures(tmp_path)


def test_metadata_network_error_does_not_inherit_prior_batch_http_200(tmp_path):
    calls, now = [], [100.0]
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"query": {"pages": {}}})
        raise httpx.ConnectError("Fixture network failure", request=request)
    data = dataset(21)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            curated.collect_metadata(seeds(data), tmp_path, client=client,
                clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    assert len(calls) == 2
    stop = json.loads((tmp_path / "acquisition-stop.json").read_text())
    assert stop["http_status"] is None


def test_explicit_seed_limit_caps_acquisition_at_three_serial_paced_requests(tmp_path):
    data = dataset(24); checked = curated.validate_seeds(seeds(data, files=2), data)
    now, starts = [100.0], []
    def sleep(seconds): now[0] += seconds
    def handler(_):
        starts.append(now[0])
        return httpx.Response(200, json={"query": {"pages": {}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = curated.collect_metadata(checked, tmp_path, client=client, clock=lambda: now[0], sleep=sleep)
    assert result["requested_files"] == 48 and len(result["captures"]) == 3
    assert starts == [100.0, 110.0, 120.0]
    extra = dataset(25)
    with pytest.raises(ValueError, match="one to 24"):
        curated.validate_seeds(seeds(extra), extra)


def test_apply_is_idempotent_and_preserves_primary_facts_including_closure(tmp_path):
    data = dataset(); original = copy.deepcopy(data)
    sidecar = compile_fixture(tmp_path, data=data)
    result = curated.apply_curated_commons(data, sidecar)
    assert data == original
    poi = result["pois"][0]
    assert poi["operating_status"] == "closed" and poi["recommendable"] is False
    for key, value in original["pois"][0].items():
        if key not in {"photos", "image"}:
            assert poi[key] == value
    assert len(poi["photos"]) == 1 and len(poi["media_identity_evidence"]) == 1
    assert curated.apply_curated_commons(result, sidecar) == result
    changed = copy.deepcopy(data)
    changed["pois"][0]["lat"] += .01
    with pytest.raises(ValueError, match="target identity changed"):
        curated.apply_curated_commons(changed, sidecar)


def test_download_checks_actual_image_and_retains_local_content_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(curated.time, "sleep", lambda _: None)
    sidecar = compile_fixture(tmp_path)
    content = png_bytes(); calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=content, headers={"content-type": "image/png"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cached = curated.cache_photos(sidecar, tmp_path / "photos", client=client)
        replay = curated.cache_photos(cached, tmp_path / "photos", client=client)
    photo = cached["assignments"][0]["photo"]
    assert len(calls) == 1 and replay == cached
    assert photo["url"].startswith("/photos/") and photo["url"].endswith(".png")
    assert photo["asset_sha256"] == hashlib.sha256(content).hexdigest()
    assert (tmp_path / "photos" / photo["url"].split("/")[-1]).read_bytes() == content
    assert sidecar["assignments"][0]["photo"]["url"].startswith("https://upload.wikimedia.org/")


def test_download_rejects_foreign_hosts_before_transport(tmp_path):
    sidecar = compile_fixture(tmp_path)
    sidecar["assignments"][0]["photo"]["thumbnail_url"] = "https://upload.wikimedia.org.evil.example/asset.jpg"
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Foreign image hosts must never be requested"))) as client:
        with pytest.raises(ValueError, match="Commons asset hosts"):
            curated.cache_photos(sidecar, tmp_path / "photos", client=client)


@pytest.mark.parametrize("problem", ["wrong_mime", "corrupt", "oversize"])
def test_bad_download_stops_without_writing_an_asset_or_retrying(tmp_path, monkeypatch, problem):
    sidecar = compile_fixture(tmp_path)
    content = b"corrupt" if problem == "corrupt" else png_bytes()
    mime = "application/json" if problem == "wrong_mime" else "image/png"
    if problem == "oversize": monkeypatch.setattr(curated, "MAX_RESPONSE", 100)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=content, headers={"content-type": mime})
    directory = tmp_path / "photos"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((ValueError, OSError)):
            curated.cache_photos(sidecar, directory, client=client)
        assert (directory / "download-stop.json").is_file()
        assert not list(directory.glob("*.png")) and not list(directory.glob("*.jpg"))
        with pytest.raises(ValueError, match="prior asset request stopped"):
            curated.cache_photos(sidecar, directory, client=client)
    assert len(calls) == 1


@pytest.mark.parametrize("problem", ["corrupt", "undersized", "hash_changed"])
def test_preexisting_asset_is_never_replaced_and_cannot_bypass_validation(tmp_path, problem):
    sidecar = compile_fixture(tmp_path)
    photo = sidecar["assignments"][0]["photo"]
    key = hashlib.sha256(photo["source_url"].encode()).hexdigest()[:20]
    directory = tmp_path / "photos"; directory.mkdir()
    path = directory / (key + ".png")
    content = b"corrupt" if problem == "corrupt" else png_bytes(size=(20, 20) if problem == "undersized" else (200, 180))
    path.write_bytes(content)
    photo["asset_sha256"] = hashlib.sha256(png_bytes(color="red") if problem == "hash_changed" else content).hexdigest()
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Existing assets must be validated without replacing or fetching them"))) as client:
        with pytest.raises((ValueError, OSError)):
            curated.cache_photos(sidecar, directory, client=client)
    assert path.read_bytes() == content


def test_supplied_sidecar_hash_cannot_override_immutable_asset_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(curated.time, "sleep", lambda _: None)
    sidecar = compile_fixture(tmp_path)
    directory = tmp_path / "photos"
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"}))) as client:
        cached = curated.cache_photos(sidecar, directory, client=client)
    photo = cached["assignments"][0]["photo"]
    path = directory / photo["url"].split("/")[-1]
    original_manifest = (directory / "asset-manifest.json").read_bytes()
    altered = png_bytes(color="red")
    path.write_bytes(altered)
    photo["asset_sha256"] = hashlib.sha256(altered).hexdigest()
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("A conflicting cached acquisition cannot be refreshed"))) as client:
        with pytest.raises(ValueError, match="retained source acquisition"):
            curated.cache_photos(cached, directory, client=client)
    assert path.read_bytes() == altered
    assert (directory / "asset-manifest.json").read_bytes() == original_manifest
