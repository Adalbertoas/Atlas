import 'package:flutter/material.dart';

import 'core/config.dart';
import 'core/session.dart';
import 'screens/connect_screen.dart';
import 'screens/shell.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await AppPrefs.load();
  final server = await prefs.server();
  runApp(AtlasApp(prefs: prefs, server: server));
}

class AtlasApp extends StatefulWidget {
  const AtlasApp({super.key, required this.prefs, this.server});

  final AppPrefs prefs;
  final ServerConfig? server;

  @override
  State<AtlasApp> createState() => _AtlasAppState();
}

class _AtlasAppState extends State<AtlasApp> {
  Session? _session;
  ServerConfig? _lastServer;

  @override
  void initState() {
    super.initState();
    if (widget.server != null) _start(widget.server!);
  }

  void _start(ServerConfig config) {
    _session?.dispose();
    _session = Session(widget.prefs, config); // Shell la arranca (start)
    _lastServer = config;
  }

  Future<void> _connected(ServerConfig config) async {
    await widget.prefs.saveServer(config);
    setState(() => _start(config));
  }

  Future<void> _disconnect() async {
    await widget.prefs.forgetServer();
    setState(() {
      _session?.dispose();
      _session = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    return MaterialApp(
      title: 'ATLAS',
      debugShowCheckedModeBanner: false,
      theme: atlasTheme(),
      home: session == null
          ? ConnectScreen(onConnected: _connected, initial: _lastServer)
          : Shell(key: ValueKey(session), session: session, onDisconnect: _disconnect),
    );
  }
}
