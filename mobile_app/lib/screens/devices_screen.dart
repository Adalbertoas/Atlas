import 'package:flutter/material.dart';

import '../models/device.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';

class DevicesScreen extends StatefulWidget {
  final ApiClient apiClient;
  const DevicesScreen({super.key, required this.apiClient});

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  List<Device> _devices = [];
  bool _loading = true;
  String? _error;
  // entity_id de un dispositivo mientras se procesa su comando — evita
  // doble tap mientras se espera la respuesta del chat.
  String? _togglingId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final devices = await widget.apiClient.listDevices();
      setState(() => _devices = devices);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'No se pudo conectar al servidor.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// El toggle no pega directo a una API de control — no existe (ver
  /// backend/app/api/v1/devices.py: solo lectura). Se manda por chat en
  /// lenguaje natural, mismo mecanismo que dashboard/app.js
  /// (renderDeviceRow) y mobile/app.js: todo pasa por el Orchestrator y el
  /// Permission Manager, ni siquiera el celular tiene un atajo directo.
  Future<void> _toggle(Device device) async {
    setState(() => _togglingId = device.id);
    final verb = device.isOn ? 'apagá' : 'encendé';
    try {
      await widget.apiClient.sendChat('$verb ${device.name}');
      await _load(); // refresca el estado real, no asume que el comando funcionó
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _togglingId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _devices.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: AtlasColors.accent));
    }
    if (_error != null && _devices.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: const TextStyle(color: AtlasColors.danger)),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Reintentar')),
          ],
        ),
      );
    }
    if (_devices.isEmpty) {
      return const Center(
        child: Text('Sin dispositivos.', style: TextStyle(color: AtlasColors.textFaint)),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      color: AtlasColors.accent,
      backgroundColor: AtlasColors.panel,
      child: ListView.separated(
        padding: const EdgeInsets.all(14),
        itemCount: _devices.length,
        separatorBuilder: (_, _) => const SizedBox(height: 8),
        itemBuilder: (context, index) => _DeviceCard(
          device: _devices[index],
          busy: _togglingId == _devices[index].id,
          onToggle: () => _toggle(_devices[index]),
        ),
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  final Device device;
  final bool busy;
  final VoidCallback onToggle;

  const _DeviceCard({required this.device, required this.busy, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AtlasColors.panel,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AtlasColors.border),
      ),
      child: Row(
        children: [
          Icon(_iconFor(device.type), color: device.isOn ? AtlasColors.accent : AtlasColors.textDim),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(device.name, style: const TextStyle(color: AtlasColors.text, fontSize: 14)),
                Text(
                  device.canToggle
                      ? '${device.room ?? "Sin sala"} · ${device.isOn ? "Encendido" : "Apagado"}'
                      : '${device.room ?? "Sin sala"} · ${device.state}',
                  style: const TextStyle(color: AtlasColors.textFaint, fontSize: 12),
                ),
              ],
            ),
          ),
          if (device.canToggle)
            busy
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: AtlasColors.accent),
                  )
                : Switch(
                    value: device.isOn,
                    activeThumbColor: AtlasColors.accent,
                    onChanged: (_) => onToggle(),
                  ),
        ],
      ),
    );
  }

  IconData _iconFor(String type) {
    switch (type) {
      case 'LIGHT':
        return Icons.lightbulb_outline;
      case 'SWITCH':
      case 'PLUG':
        return Icons.power_outlined;
      case 'FAN':
        return Icons.mode_fan_off_outlined;
      case 'TV':
        return Icons.tv_outlined;
      case 'LOCK':
        return Icons.lock_outline;
      case 'CAMERA':
        return Icons.videocam_outlined;
      case 'CLIMATE':
      case 'THERMOSTAT':
        return Icons.thermostat_outlined;
      case 'SENSOR':
        return Icons.sensors_outlined;
      default:
        return Icons.devices_other_outlined;
    }
  }
}
