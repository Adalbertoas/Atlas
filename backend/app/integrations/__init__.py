"""Integraciones con APIs externas (Fase 10): Wikipedia, clima, YouTube,
Spotify. Cada módulo es un cliente HTTP delgado y sin estado de UI —
las tools en app/tools/ los envuelven para exponerlos a la IA.

Wikipedia y clima (Open-Meteo) no requieren API key. YouTube y Spotify sí
— ver .env.example para cómo conseguirlas.
"""
