import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import 'chat_screen.dart';
import 'devices_screen.dart';
import 'login_screen.dart';

/// Shell con navegación inferior — Chat y Dispositivos son el núcleo de
/// esta primera versión (ver README de la app). El resto de lo que ya tiene
/// mobile/ (voz, gestos, Shazam, notificaciones, memoria) queda para
/// iteraciones siguientes.
class HomeScreen extends StatefulWidget {
  final ApiClient apiClient;
  const HomeScreen({super.key, required this.apiClient});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    widget.apiClient.onSessionExpired = _goToLogin;
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
    final screens = [
      ChatScreen(apiClient: widget.apiClient),
      DevicesScreen(apiClient: widget.apiClient),
    ];
    final titles = ['Chat', 'Dispositivos'];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_index]),
        actions: [
          IconButton(
            onPressed: _logout,
            icon: const Icon(Icons.logout, color: AtlasColors.textDim),
            tooltip: 'Cerrar sesión',
          ),
        ],
      ),
      body: SafeArea(child: screens[_index]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: 'Chat'),
          NavigationDestination(icon: Icon(Icons.devices_other_outlined), label: 'Dispositivos'),
        ],
      ),
    );
  }
}
