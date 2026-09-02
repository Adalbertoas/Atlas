import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../widgets/atlas_chrome.dart';
import 'automations_screen.dart';
import 'chat_screen.dart';
import 'devices_screen.dart';
import 'login_screen.dart';
import 'memory_screen.dart';
import 'notifications_screen.dart';

/// Shell con navegación inferior. Las cinco pestañas son las del dashboard
/// que tienen sentido en un celular y no dependen de hardware que la app
/// nativa todavía no usa: voz, Shazam y gestos siguen existiendo solo en la
/// PWA `mobile/` (ver el README de la app).
class HomeScreen extends StatefulWidget {
  final ApiClient apiClient;
  const HomeScreen({super.key, required this.apiClient});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  int _unread = 0;
  bool? _online;
  Timer? _pingTimer;

  static const _titles = ['Conversación', 'Dispositivos', 'Automatizaciones', 'Notificaciones', 'Memoria'];
  static const _subtitles = [
    'Hablá con ATLAS',
    'Tu casa, en una lista',
    'Tus rutinas guardadas',
    'Lo que ATLAS te avisó',
    'Lo que ATLAS recuerda de vos',
  ];

  @override
  void initState() {
    super.initState();
    widget.apiClient.onSessionExpired = _goToLogin;
    _ping();
    // El punto de estado tiene que envejecer solo: si el backend se cae
    // mientras la app está abierta y no tocás nada, sin este timer seguiría
    // en verde indefinidamente.
    _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) => _ping());
  }

  @override
  void dispose() {
    _pingTimer?.cancel();
    super.dispose();
  }

  Future<void> _ping() async {
    final ok = await widget.apiClient.ping();
    if (mounted) setState(() => _online = ok);
  }

  void _goToLogin() {
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => LoginScreen(apiClient: widget.apiClient)),
      (route) => false,
    );
  }

  Future<void> _logout() async {
    await widget.apiClient.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => LoginScreen(apiClient: widget.apiClient)),
    );
  }

  @override
  Widget build(BuildContext context) {
    // IndexedStack y no una lista indexada: cambiar de pestaña no debe
    // perder la conversación en curso ni recargar las listas cada vez.
    final views = IndexedStack(
      index: _index,
      children: [
        ChatScreen(apiClient: widget.apiClient),
        DevicesScreen(apiClient: widget.apiClient),
        AutomationsScreen(apiClient: widget.apiClient),
        NotificationsScreen(
          apiClient: widget.apiClient,
          onUnreadChanged: (count) => setState(() => _unread = count),
        ),
        MemoryScreen(apiClient: widget.apiClient),
      ],
    );

    return Scaffold(
      appBar: AtlasTopBar(
        title: _titles[_index],
        subtitle: _subtitles[_index],
        online: _online,
        actions: [
          AtlasIconButton(icon: Icons.logout, tooltip: 'Cerrar sesión', onPressed: _logout),
        ],
      ),
      body: SafeArea(top: false, child: views),
      bottomNavigationBar: NavigationBar(
        height: 62,
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline, color: AtlasColors.textDim),
            selectedIcon: Icon(Icons.chat_bubble, color: AtlasColors.accent),
            label: 'Chat',
          ),
          const NavigationDestination(
            icon: Icon(Icons.devices_other_outlined, color: AtlasColors.textDim),
            selectedIcon: Icon(Icons.devices_other, color: AtlasColors.accent),
            label: 'Casa',
          ),
          const NavigationDestination(
            icon: Icon(Icons.auto_mode_outlined, color: AtlasColors.textDim),
            selectedIcon: Icon(Icons.auto_mode, color: AtlasColors.accent),
            label: 'Rutinas',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _unread > 0,
              label: Text('$_unread'),
              backgroundColor: AtlasColors.accent,
              textColor: AtlasColors.accentOn,
              child: const Icon(Icons.notifications_none, color: AtlasColors.textDim),
            ),
            selectedIcon: const Icon(Icons.notifications, color: AtlasColors.accent),
            label: 'Avisos',
          ),
          const NavigationDestination(
            icon: Icon(Icons.psychology_outlined, color: AtlasColors.textDim),
            selectedIcon: Icon(Icons.psychology, color: AtlasColors.accent),
            label: 'Memoria',
          ),
        ],
      ),
    );
  }
}
