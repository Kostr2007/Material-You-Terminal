# `nix flake check`: render themes and make sure every tool accepts its config.
{ pkgs, self }:

let
  mkTheme = self.lib.mkTheme pkgs;

  # Fails on unknown options and unparsable values.
  kittyCheck = pkgs.writeShellScript "kitty-check" ''
    res=$(${pkgs.kitty}/bin/kitty +runpy "
    import sys
    from kitty.config import load_config
    bad = []
    load_config(sys.argv[-1], accumulate_bad_lines=bad)
    for b in bad:
        print('bad line', b.number, repr(b.line), b.exception)
    " "$1" 2>&1)
    echo "$res"
    if echo "$res" | grep -qiE "bad line|unknown|error"; then exit 1; fi
  '';

  validate = name: theme: pkgs.runCommandLocal "myt-check-${name}"
    {
      nativeBuildInputs = with pkgs; [ fish starship fastfetch kitty python3 ];
    } ''
    export HOME=$TMPDIR
    t=${theme}

    echo "== palette"
    python3 -c "import json,sys; c=json.load(open('$t/palette.json'))['colors']; assert all(f'ansi{i}' in c for i in range(16)); print(c['primary'], c['surface'])"

    echo "== no unrendered placeholders"
    ! grep -n '{{' $t/kitty.conf $t/colors.fish $t/starship.toml $t/fastfetch.jsonc

    echo "== fish"
    fish --no-config -c "source $t/colors.fish; set_color \$fish_color_command; echo ok"

    echo "== starship"
    res=$(STARSHIP_CONFIG=$t/starship.toml STARSHIP_LOG=warn starship prompt 2>&1 >/dev/null || true)
    if [ -n "$res" ]; then echo "$res"; exit 1; fi

    echo "== fastfetch"
    res=$(fastfetch --config $t/fastfetch.jsonc --pipe true --logo none 2>&1)
    echo "$res" | head -5
    if echo "$res" | grep -iE "error|unknown|invalid"; then exit 1; fi

    echo "== kitty"
    ${kittyCheck} $t/kitty.conf

    touch $out
  '';
in
{
  package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
  dark = validate "dark" (mkTheme { });
  light = validate "light" (mkTheme { mode = "light"; source.color = "#B3261E"; scheme = "scheme-expressive"; });
  overrides = validate "overrides" (mkTheme { overrides = { primary = "#00ff88"; ansi4 = "#3366ff"; }; });
}
