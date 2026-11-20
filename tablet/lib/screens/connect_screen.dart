import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../ui/theme.dart';

/// Primera vez: a qué PC con ATLAS conectarse.
class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.onConnected, this.initial});

  final ValueChanged<ServerConfig> onConnected;
  final ServerConfig? initial;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late final _url = TextEditingController(text: widget.initial?.baseUrl ?? 'https://atlas.sirinetrd.com');
  late final _password = TextEditingController(text: widget.initial?.password ?? '');
  bool _busy = false;
  bool _hidePassword = true;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _password.dispose();
    super.dispose();
  }

  String _normalized(String raw) {
    var url = raw.trim();
    if (url.isEmpty) return url;
    if (!url.contains('://')) url = 'https://$url';
    var uri = Uri.parse(url);
    // Sin puerto: una IP de la red local usa el del backend (8000); un dominio, el estándar.
    if (!uri.hasPort && RegExp(r'^\d+\.\d+\.\d+\.\d+$').hasMatch(uri.host)) uri = uri.replace(port: 8000);
    return uri.replace(path: uri.path.replaceAll(RegExp(r'/+$'), '')).toString();
  }

  Future<void> _connect() async {
    final url = _normalized(_url.text);
    final uri = Uri.tryParse(url);
    if (uri == null || uri.host.isEmpty) {
      setState(() => _error = 'Escribe la dirección de ATLAS, por ejemplo https://atlas.sirinetrd.com');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      String? fingerprint;
      try {
        fingerprint = await AtlasApi.probeFingerprint(uri);
      } catch (_) {
        throw AtlasException('No encuentro ATLAS en $url. Revisa que el backend esté corriendo y que la dirección sea correcta.');
      }
      if (fingerprint != null && fingerprint != widget.initial?.fingerprint) {
        if (!mounted || !await _confirmFingerprint(fingerprint)) return;
      }
      final config = ServerConfig(baseUrl: url, fingerprint: fingerprint, password: _password.text);
      final api = AtlasApi(config);
      try {
        await api.health();
        await api.login();
        await api.verifyAccess();
      } finally {
        api.close();
      }
      widget.onConnected(config);
    } on AtlasException catch (error) {
      setState(() => _error = error.status == 401 || error.status == 403
          ? 'ATLAS pide contraseña: escribe la de ATLAS_PASSWORD del backend.'
          : error.message);
    } catch (error) {
      setState(() => _error = 'No se pudo conectar: $error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _confirmFingerprint(String fingerprint) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('¿Confiar en esta PC?'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('El backend de ATLAS usa un certificado propio. Esta es su huella:'),
          const SizedBox(height: 12),
          SelectableText(AtlasApi.prettyFingerprint(fingerprint),
              style: const TextStyle(fontFamily: 'monospace', color: Hud.cyan, fontSize: 13, height: 1.5)),
          const SizedBox(height: 12),
          const Text(
            'Si confías, la tablet solo hablará con esta PC: si otro equipo intentara hacerse pasar por ATLAS, '
            'la conexión se rechazará.',
            style: TextStyle(color: Hud.muted, fontSize: 13),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confiar y conectar')),
        ],
      ),
    );
    return accepted ?? false;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: HudPanel(
                title: 'Conectar con ATLAS',
                icon: Icons.hub_outlined,
                padding: const EdgeInsets.all(22),
                child: AutofillGroup(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    const Text('A.T.L.A.S',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 34, fontWeight: FontWeight.w700, letterSpacing: 8, color: Hud.cyan)),
                    const SizedBox(height: 6),
                    const Text('Usa la dirección pública de ATLAS o la de tu PC en la red local.',
                        textAlign: TextAlign.center, style: TextStyle(color: Hud.muted)),
                    const SizedBox(height: 24),
                    TextField(
                      controller: _url,
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      decoration: const InputDecoration(labelText: 'Dirección de ATLAS', prefixIcon: Icon(Icons.dns_outlined)),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _password,
                      obscureText: _hidePassword,
                      autofillHints: const [AutofillHints.password],
                      onSubmitted: (_) => _connect(),
                      decoration: InputDecoration(
                        labelText: 'Contraseña de ATLAS (si la pide)',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(_hidePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                          onPressed: () => setState(() => _hidePassword = !_hidePassword),
                        ),
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 14),
                      Text(_error!, style: const TextStyle(color: Hud.red)),
                    ],
                    const SizedBox(height: 22),
                    FilledButton.icon(
                      onPressed: _busy ? null : _connect,
                      icon: _busy
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.link),
                      label: Text(_busy ? 'Conectando…' : 'Conectar'),
                    ),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
