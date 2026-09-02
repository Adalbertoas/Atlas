import 'package:flutter/material.dart';

import '../models/device.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../widgets/atlas_chrome.dart';

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
    setState(() => _error = null);
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
    return AtlasResourceList<Device>(
      items: _devices,
      loading: _loading,
      error: _error,
      emptyMessage: 'Sin dispositivos.',
      onRefresh: _load,
      itemBuilder: (context, device) => _DeviceCard(
        device: device,
        busy: _togglingId == device.id,
        onToggle: () => _toggle(device),
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
    return AtlasCard(
      icon: _iconFor(device.type),
      iconColor: device.isOn ? AtlasColors.accent : AtlasColors.textDim,
      title: device.name,
      subtitle: device.canToggle
          ? '${device.room ?? "Sin sala"} · ${device.isOn ? "Encendido" : "Apagado"}'
          : '${device.room ?? "Sin sala"} · ${device.state}',
      trailing: !device.canToggle
          ? null
          : busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: AtlasColors.accent),
                )
              : Switch(
                  value: device.isOn,
                  activeThumbColor: AtlasColors.accent,
                  activeTrackColor: AtlasColors.accentSoft,
                  inactiveThumbColor: AtlasColors.textDim,
                  inactiveTrackColor: AtlasColors.panel2,
                  onChanged: (_) => onToggle(),
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
