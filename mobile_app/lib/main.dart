import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/api_client.dart';
import 'theme/atlas_theme.dart';

void main() {
  runApp(const AtlasApp());
}

class AtlasApp extends StatefulWidget {
  const AtlasApp({super.key});

  @override
  State<AtlasApp> createState() => _AtlasAppState();
}

class _AtlasAppState extends State<AtlasApp> {
  final _apiClient = ApiClient();
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _apiClient.loadFromStorage().then((_) {
      if (mounted) setState(() => _ready = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ATLAS',
      debugShowCheckedModeBanner: false,
      theme: buildAtlasTheme(),
      home: !_ready
          ? const Scaffold(
              backgroundColor: AtlasColors.bg,
              body: Center(child: CircularProgressIndicator(color: AtlasColors.accent)),
            )
          // Un token guardado no garantiza que siga siendo válido (pudo
          // expirar o quedar revocado por /auth/logout desde otro
          // dispositivo) — HomeScreen/ApiClient lo descubren en el primer
          // pedido real y ahí se puede mandar de vuelta al login si hace
          // falta; acá solo se decide la pantalla inicial.
          : _apiClient.isLoggedIn
              ? HomeScreen(apiClient: _apiClient)
              : LoginScreen(apiClient: _apiClient),
    );
  }
}
