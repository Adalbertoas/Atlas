from __future__ import annotations

import numpy as np

from atlas_desktop.wake_word import contains_wake_word, has_speech


def test_has_speech_detects_loud_chunk():
    loud = np.full(1000, 5000, dtype=np.int16)
    assert has_speech(loud, threshold=300.0) is True


def test_has_speech_ignores_silence():
    silence = np.zeros(1000, dtype=np.int16)
    assert has_speech(silence, threshold=300.0) is False


def test_has_speech_handles_empty_chunk():
    assert has_speech(np.array([], dtype=np.int16)) is False


def test_contains_wake_word_matches_when_said_first():
    assert contains_wake_word("Atlas, que hora es?") is True
    assert contains_wake_word("ATLAS que hora es") is True
    assert contains_wake_word("hola atlas") is True  # "atlas" sigue entre las 2 primeras palabras


def test_contains_wake_word_false_when_absent():
    assert contains_wake_word("hola, que hora es?") is False


def test_contains_wake_word_ignores_mentions_mid_sentence():
    # Caso real que causaba falsos positivos: una conversación de fondo que
    # menciona "atlas" de pasada no debe disparar el asistente.
    assert contains_wake_word("estábamos viendo un mapa, el atlas ese que compramos") is False


def test_contains_wake_word_handles_empty_text():
    assert contains_wake_word("") is False
    assert contains_wake_word(None) is False
