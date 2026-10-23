# fastfetch as a Material You "card". Colors are template placeholders that
# material-you-terminal fills in with the active palette.
{ logo ? null }:

let
  key = icon: name: "${icon}  ${name}";
  system = "{{primary}}";
  desktop = "{{tertiary}}";
  hardware = "{{secondary}}";
in
{
  "$schema" = "https://github.com/fastfetch-cli/fastfetch/raw/dev/doc/json_schema.json";

  logo = {
    padding = { top = 1; left = 2; right = 4; };
    color = {
      "1" = "{{primary}}";
      "2" = "{{tertiary}}";
      "3" = "{{secondary}}";
      "4" = "{{primary_container}}";
      "5" = "{{tertiary_container}}";
      "6" = "{{secondary_container}}";
    };
  } // (if logo == null then { type = "small"; } else { source = logo; });

  display = {
    separator = "  ";
    color = {
      keys = "{{primary}}";
      title = "{{primary}}";
      output = "{{on_surface}}";
      separator = "{{outline}}";
    };
    key.width = 13;
    bar = {
      char = { elapsed = "━"; total = "━"; };
      border = { left = ""; right = ""; };
      color = { elapsed = "{{primary}}"; total = "{{surface_container_highest}}"; };
      width = 14;
    };
    percent = {
      type = [ "bar" "num" ];
      color = { green = "{{ansi2}}"; yellow = "{{ansi3}}"; red = "{{error}}"; };
    };
  };

  modules = [
    {
      type = "title";
      format = "{user-name-colored}{at-symbol-colored}{host-name-colored}";
      color = { user = "{{primary}}"; at = "{{outline}}"; host = "{{tertiary}}"; };
    }
    { type = "separator"; string = "─"; outputColor = "{{outline_variant}}"; }

    { type = "os"; key = key "" "os"; keyColor = system; }
    { type = "kernel"; key = key "" "kernel"; keyColor = system; }
    { type = "packages"; format = "{all}"; key = key "󰏖" "packages"; keyColor = system; }
    { type = "uptime"; key = key "󰥔" "uptime"; keyColor = system; }

    { type = "shell"; key = key "" "shell"; keyColor = desktop; }
    { type = "terminal"; key = key "" "terminal"; keyColor = desktop; }
    { type = "wm"; key = key "" "wm"; keyColor = desktop; }

    { type = "cpu"; key = key "" "cpu"; keyColor = hardware; showPeCoreCount = true; }
    { type = "gpu"; key = key "󰍹" "gpu"; keyColor = hardware; }
    { type = "memory"; key = key "󰍛" "memory"; keyColor = hardware; }
    { type = "disk"; key = key "󰋊" "disk"; keyColor = hardware; folders = "/"; format = "{size-percentage-bar} {size-used} / {size-total}"; }

    "break"
    { type = "colors"; symbol = "circle"; paddingLeft = 2; }
  ];
}
