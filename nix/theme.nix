# Renders a complete theme directory (kitty.conf, colors.fish, starship.toml,
# fastfetch.jsonc, palette.json) at build time.
{ lib, runCommandLocal, writeText, myt }:

{ name ? "material-you-theme"
, source ? { color = "#6750A4"; }
, mode ? "dark"
, scheme ? "scheme-tonal-spot"
, contrast ? 0.0
, customColors ? { }
, overrides ? { }
, templates
}:

let
  spec = writeText "${name}-spec.json" (builtins.toJSON {
    inherit source mode scheme contrast customColors overrides;
    templates = lib.mapAttrs (_: t: "${t}") templates;
  });
in
runCommandLocal name { } ''
  ${lib.getExe myt} --config ${spec} generate --out $out
''
