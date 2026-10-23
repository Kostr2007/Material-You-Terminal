{
  description = "Material You for your terminal: kitty, fish, starship & fastfetch themed from your wallpaper";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      overlays.default = final: _prev: {
        material-you-terminal = final.callPackage ./nix/package.nix { };
      };

      packages = forAllSystems (pkgs:
        let
          myt = pkgs.callPackage ./nix/package.nix { };
          mkTheme = self.lib.mkTheme pkgs;
        in
        {
          default = myt;
          myt = myt;
          # `nix build .#theme-preview` renders the default dark theme.
          theme-preview = mkTheme { };
          theme-preview-light = mkTheme { mode = "light"; };
        });

      lib = {
        # mkTheme pkgs { source = { image = ./wall.png; }; mode = "dark"; ... }
        mkTheme = pkgs: args:
          let
            myt = pkgs.callPackage ./nix/package.nix { };
            templates = import ./nix/templates.nix { inherit lib pkgs; } {
              starshipSettings = args.starshipSettings or { };
              fastfetchSettings = args.fastfetchSettings or { };
              fastfetchLogo = args.fastfetchLogo or null;
            };
          in
          pkgs.callPackage ./nix/theme.nix { inherit myt; }
            ({ inherit templates; } // removeAttrs args [ "starshipSettings" "fastfetchSettings" "fastfetchLogo" ]);
      };

      homeManagerModules = {
        default = self.homeManagerModules.material-you-terminal;
        material-you-terminal = import ./modules/home-manager.nix { inherit self; };
      };

      nixosModules = {
        default = self.nixosModules.material-you-terminal;
        material-you-terminal = import ./modules/nixos.nix { inherit self; };
      };

      checks = forAllSystems (pkgs: import ./nix/checks.nix { inherit pkgs self; });

      formatter = forAllSystems (pkgs: pkgs.nixpkgs-fmt);

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [ python3 matugen kitty fish starship fastfetch nixpkgs-fmt ];
        };
      });
    };
}
