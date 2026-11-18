def test_transcribe(make_client) -> None:
    client = make_client([])
    response = client.post(
        "/api/speech/transcribe", files={"audio": ("answer.webm", b"fake-audio", "audio/webm")}
    )
    assert response.status_code == 200
    assert response.json() == {"text": "I am work as developer"}


def test_transcribe_rejects_empty_recording(make_client) -> None:
    client = make_client([])
    response = client.post(
        "/api/speech/transcribe", files={"audio": ("answer.webm", b"", "audio/webm")}
    )
    assert response.status_code == 422


def test_synthesize_returns_wav(make_client) -> None:
    client = make_client([])
    response = client.post("/api/speech/synthesize", json={"text": "Hello Anna!"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFHello Anna!"


def test_speech_errors_are_reported(make_client, speech) -> None:
    client = make_client([])
    speech.fail = True
    assert client.post("/api/speech/synthesize", json={"text": "Hi"}).status_code == 500
    transcribe = client.post(
        "/api/speech/transcribe", files={"audio": ("a.webm", b"x", "audio/webm")}
    )
    assert transcribe.status_code == 500
