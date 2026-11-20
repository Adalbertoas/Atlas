// Palabra de activación sobre texto transcrito y limpieza de alucinaciones de
// Whisper. Port directo de desktop/electron/src/atlas/voice/wakeWord.ts: la
// tablet y la PC reconocen "Atlas" exactamente igual.

const wakeWord = 'atlas';

/// Sesga a Whisper hacia la palabra de activación (probado en el escritorio:
/// con "Atlas." solo, alucinaba "¡Adiós!" sobre silencio).
const wakePrompt = 'Hola Atlas.';

/// Formas en que Whisper suele escribir "Atlas" mal oído.
const _variants = {'atlas', 'atla', 'atlass', 'hatlas', 'adlas', 'attlas', 'aplas', 'atlaz', 'atlax', 'athlas'};

/// Palabras reales a distancia 1 de "atlas" que no deben activar a ATLAS.
const _notWake = {'aulas', 'atras', 'atlan'};

/// Muletillas que pueden ir antes del nombre: "oye Atlas", "hola Atlas".
const _fillers = {'oye', 'hola', 'ey', 'hey', 'eh', 'che', 'a', 'ah', 'bueno', 'ok', 'okay', 'vale'};

const _accents = {
  'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a', 'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e', 'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i',
  'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o', 'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u', 'ñ': 'n', 'ç': 'c',
};

/// Minúsculas y sin tildes (como normalize("NFD") + quitar diacríticos en JS).
String fold(String text) {
  final lower = text.toLowerCase();
  final out = StringBuffer();
  for (final rune in lower.runes) {
    final char = String.fromCharCode(rune);
    out.write(_accents[char] ?? char);
  }
  return out.toString();
}

List<String> words(String text) => [for (final m in RegExp(r'[a-z0-9]+').allMatches(fold(text))) m.group(0)!];

int levenshtein(String a, String b) {
  if (a == b) return 0;
  var previous = List<int>.generate(b.length + 1, (i) => i);
  for (var i = 1; i <= a.length; i++) {
    final current = <int>[i];
    for (var j = 1; j <= b.length; j++) {
      final cost = a[i - 1] == b[j - 1] ? 0 : 1;
      current.add([previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost].reduce((x, y) => x < y ? x : y));
    }
    previous = current;
  }
  return previous[b.length];
}

bool _isWakeToken(String token) {
  if (_notWake.contains(token)) return false;
  if (_variants.contains(token)) return true;
  return token.length >= 5 && token.length <= 6 && levenshtein(token, wakeWord) <= 1;
}

class WakeMatch {
  const WakeMatch(this.detected, this.command);

  final bool detected;

  /// Lo que se dijo después del nombre ("Atlas, ¿qué hora es?" → "¿qué hora es?").
  final String command;
}

/// Solo cuenta si el nombre va al principio (tras una muletilla como mucho),
/// igual que cuando se llama a alguien. También acepta "at las".
WakeMatch detectWakeWord(String text) {
  final original = text.trim();
  final tokens = [
    for (final m in RegExp(r'[\p{L}\p{N}]+', unicode: true).allMatches(original))
      (norm: words(m.group(0)!).firstOrNull ?? '', end: m.end),
  ];
  var index = 0;
  while (index < tokens.length && index < 2 && _fillers.contains(tokens[index].norm) && !_isWakeToken(tokens[index].norm)) {
    index++;
  }
  if (index >= tokens.length) return const WakeMatch(false, '');
  var end = -1;
  if (_isWakeToken(tokens[index].norm)) {
    end = tokens[index].end;
  } else if (tokens[index].norm == 'at' && index + 1 < tokens.length && tokens[index + 1].norm == 'las') {
    end = tokens[index + 1].end;
  }
  if (end < 0) return const WakeMatch(false, '');
  final rest = original.substring(end);
  final command = rest.replaceFirst(RegExp(r'^[\s,.;:!¡?¿…-]+'), '').trim();
  // Conserva el signo de apertura si la pregunta empezaba justo después del nombre.
  final opener = RegExp(r'^[\s,]*([¿¡])').firstMatch(rest)?.group(1) ?? '';
  return WakeMatch(true, command.isNotEmpty && opener.isNotEmpty && !command.startsWith(opener) ? '$opener$command' : command);
}

/// Frases que Whisper inventa sobre ruido o silencio (subtítulos de YouTube).
final _hallucinations = [
  RegExp(r'^gracias( por (ver|mirar)( el video)?)?$'),
  RegExp(r'^subtitulos? (realizados|hechos|creados) por'),
  RegExp(r'^subtitulado por'),
  RegExp(r'amara\.?org'),
  RegExp(r'^suscribete'),
  RegExp(r'^adios$'),
  RegExp(r'^musica$'),
  RegExp(r'^aplausos$'),
  RegExp(r'^risas$'),
  RegExp(r'^\.+$'),
];

/// Texto vacío si lo transcrito es solo una alucinación típica de Whisper.
String cleanTranscript(String text) {
  final trimmed = text.replaceAll(RegExp(r'\s+'), ' ').trim();
  final plain = words(trimmed).join(' ');
  if (plain.isEmpty) return '';
  final raw = fold(trimmed).replaceAll(RegExp(r'[¡!¿?.,]+'), '').trim();
  if (_hallucinations.any((p) => p.hasMatch(plain) || p.hasMatch(raw))) return '';
  return trimmed;
}
