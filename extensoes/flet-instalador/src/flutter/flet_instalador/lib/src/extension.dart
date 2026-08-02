import 'package:flet/flet.dart';

import 'flet_instalador.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "FletInstalador":
        return FletInstaladorService(control: control);
      default:
        return null;
    }
  }
}
