# Builds the template set (with {{role}} placeholders) that every theme is
# rendered from. Starship and fastfetch are described as Nix attrsets so users
# can merge their own settings in.
{ lib, pkgs }:

{ starshipSettings ? { }
, fastfetchSettings ? { }
, fastfetchLogo ? null
}:

let
  toml = pkgs.formats.toml { };
  json = pkgs.formats.json { };

  starshipBase = lib.recursiveUpdate (import ../modules/starship.nix { inherit lib; }) starshipSettings;
  fastfetch = lib.recursiveUpdate (import ../modules/fastfetch.nix { logo = fastfetchLogo; }) fastfetchSettings;

  starship = pkgs.runCommandLocal "starship.toml" { } ''
    cat ${toml.generate "starship-base.toml" starshipBase} ${../templates/starship-palette.toml} > $out
  '';
in
{
  "kitty.conf" = ../templates/kitty.conf;
  "colors.fish" = ../templates/colors.fish;
  "starship.toml" = starship;
  "fastfetch.jsonc" = json.generate "fastfetch.jsonc" fastfetch;
}
