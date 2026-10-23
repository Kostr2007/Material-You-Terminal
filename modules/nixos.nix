{ self }:

{ config, lib, pkgs, options, ... }:

let
  cfg = config.programs.material-you-terminal;
in
{
  options.programs.material-you-terminal = {
    enable = lib.mkEnableOption ''
      system-wide support for material-you-terminal: fish as an available login
      shell, the `myt` tool and the default font. Per-user theming is configured
      with home-manager (`home-manager.users.<name>.programs.material-you-terminal`)'';

    font = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = if pkgs ? nerd-fonts then pkgs.nerd-fonts.roboto-mono else null;
      defaultText = lib.literalExpression "pkgs.nerd-fonts.roboto-mono";
      description = "Font installed system-wide.";
    };
  };

  config = lib.mkMerge [
    # Make the home-manager module available to every user when home-manager
    # is used as a NixOS module.
    (lib.optionalAttrs (options ? home-manager) {
      home-manager.sharedModules = [ self.homeManagerModules.default ];
    })

    (lib.mkIf cfg.enable {
      programs.fish.enable = true;
      environment.systemPackages = [ (pkgs.callPackage ../nix/package.nix { }) ];
      fonts.packages = lib.optional (cfg.font != null) cfg.font;
    })
  ];
}
