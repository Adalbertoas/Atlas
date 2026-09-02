import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../widgets/atlas_chrome.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  final ApiClient apiClient;
  const LoginScreen({super.key, required this.apiClient});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _passwordController = TextEditingController();
  final _urlController = TextEditingController();
  bool _showAdvanced = false;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _urlController.text = widget.apiClient.baseUrl ?? '';
  }

  @override
  void dispose() {
    _passwordController.dispose();
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) {
      setState(() => _error = 'Ingresá la URL del servidor (ej. http://192.168.1.50:8000).');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await widget.apiClient.setBaseUrl(url);
      await widget.apiClient.login(_passwordController.text);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => HomeScreen(apiClient: widget.apiClient)),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'No se pudo conectar al servidor.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 360),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const AtlasBrandMark(size: 58),
                  const SizedBox(height: 14),
                  const Text(
                    'ATLAS',
                    style: TextStyle(
                      fontFamily: AtlasFonts.display,
                      fontSize: 31,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 6.2,
                      color: AtlasColors.text,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Tu asistente personal inteligente',
                    style: TextStyle(color: AtlasColors.textDim, fontSize: 13.5),
                  ),
                  const SizedBox(height: 28),
                  TextField(
                    controller: _passwordController,
                    obscureText: true,
                    autofillHints: const [AutofillHints.password],
                    decoration: const InputDecoration(hintText: 'Contraseña'),
                    onSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 10),
                  // URL del servidor — colapsada por defecto (mismo criterio
                  // que <details id="advanced-details"> en dashboard/index.html):
                  // no todos necesitan cambiarla, y en el celular casi siempre
                  // hace falta (no hay location.hostname para autodetectarla).
                  InkWell(
                    onTap: () => setState(() => _showAdvanced = !_showAdvanced),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          _showAdvanced ? 'Ocultar avanzado' : 'Avanzado',
                          style: const TextStyle(color: AtlasColors.textFaint, fontSize: 13),
                        ),
                        Icon(
                          _showAdvanced ? Icons.expand_less : Icons.expand_more,
                          size: 18,
                          color: AtlasColors.textFaint,
                        ),
                      ],
                    ),
                  ),
                  if (_showAdvanced) ...[
                    const SizedBox(height: 8),
                    TextField(
                      controller: _urlController,
                      keyboardType: TextInputType.url,
                      decoration: const InputDecoration(
                        hintText: 'URL del servidor (ej. http://192.168.1.50:8000)',
                      ),
                    ),
                  ],
                  const SizedBox(height: 18),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _loading ? null : _submit,
                      child: _loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: AtlasColors.accentOn),
                            )
                          : const Text('Entrar'),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: AtlasColors.danger, fontSize: 13)),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
