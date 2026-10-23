{ self }:

{ config, lib, pkgs, ... }:

let
  inherit (lib) mkOption mkEnableOption mkIf mkMerge mkDefault types literalExpression;

  cfg = config.programs.material-you-terminal;
  myt = cfg.package;
  anim = cfg.animations.enable;

  templates = import ../nix/templates.nix { inherit lib pkgs; } {
    starshipSettings = cfg.starship.settings;
    fastfetchSettings = cfg.fastfetch.settings;
    fastfetchLogo = cfg.fastfetch.logo;
  };

  source =
    if cfg.source.image != null
    then { image = "${cfg.source.image}"; }
    else { color = cfg.source.color; };

  theme = pkgs.callPackage ../nix/theme.nix { inherit myt; } {
    inherit source templates;
    inherit (cfg) mode scheme contrast customColors;
    overrides = cfg.palette;
  };

  stateTheme = "${config.xdg.stateHome}/material-you-terminal/theme";
  themeDir = if cfg.dynamic.enable then stateTheme else "${theme}";

  # What `myt` reads at runtime.
  runtimeConfig = {
    inherit source templates themeDir;
    inherit (cfg) mode scheme contrast customColors;
    overrides = cfg.palette;
    dynamic = cfg.dynamic.enable;
    seedDir = "${theme}";
    matugen = lib.getExe pkgs.matugen;
    animations = anim;
    hooks = cfg.dynamic.hooks;
    kitty = {
      socketGlob = "\${XDG_RUNTIME_DIR}/kitty-myt-*";
      transitionMs = cfg.animations.transitionMs;
      easing = "standard";
    };
  };

  wallpaper =
    if cfg.dynamic.wallpaper != null && lib.hasPrefix "~/" cfg.dynamic.wallpaper
    then "${config.home.homeDirectory}/${lib.removePrefix "~/" cfg.dynamic.wallpaper}"
    else cfg.dynamic.wallpaper;

  fastfetchCmd = "fastfetch --config ${themeDir}/fastfetch.jsonc";

  # fish runs fastfetch itself (so it detects the right shell) and myt only
  # animates the output.
  fastfetchGreeting =
    if anim then "${fastfetchCmd} --pipe false | myt reveal" else fastfetchCmd;

  greeting = {
    none = "";
    fastfetch = fastfetchGreeting;
    ripple = "myt ripple";
    both = ''
      myt ripple
      ${fastfetchGreeting}
    '';
  }.${cfg.fish.greeting};

  defaultFont =
    if pkgs ? nerd-fonts then pkgs.nerd-fonts.roboto-mono
    else pkgs.nerdfonts.override { fonts = [ "RobotoMono" ]; };
in
{
  options.programs.material-you-terminal = {
    enable = mkEnableOption "Material You theming for kitty, fish, starship and fastfetch";

    package = mkOption {
      type = types.package;
      default = pkgs.callPackage ../nix/package.nix { };
      defaultText = literalExpression "material-you-terminal (myt)";
      description = "The `myt` command line tool.";
    };

    source = {
      color = mkOption {
        type = types.strMatching "#?[0-9a-fA-F]{6}";
        default = "#6750A4";
        example = "#3F6FD8";
        description = "Seed color the Material You scheme is generated from.";
      };
      image = mkOption {
        type = types.nullOr types.path;
        default = null;
        example = literalExpression "./wallpapers/forest.jpg";
        description = ''
          Wallpaper to extract the seed color from at build time (overrides `color`).
          Use a Nix path literal so the image is copied into the store.
        '';
      };
    };

    mode = mkOption {
      type = types.enum [ "dark" "light" ];
      default = "dark";
      description = "Dark or light scheme.";
    };

    scheme = mkOption {
      type = types.enum [
        "scheme-tonal-spot"
        "scheme-content"
        "scheme-expressive"
        "scheme-fidelity"
        "scheme-fruit-salad"
        "scheme-monochrome"
        "scheme-neutral"
        "scheme-rainbow"
        "scheme-vibrant"
      ];
      default = "scheme-tonal-spot";
      description = "Material You scheme variant (tonal-spot is the Android default).";
    };

    contrast = mkOption {
      type = types.numbers.between (-1) 1;
      default = 0.0;
      description = "Contrast level from -1 (reduced) to 1 (high).";
    };

    palette = mkOption {
      type = types.attrsOf (types.strMatching "#?[0-9a-fA-F]{6}");
      default = { };
      example = { primary = "#D0BCFF"; ansi4 = "#82AAFF"; };
      description = ''
        Overrides for individual roles (`primary`, `surface_container_high`, …)
        or terminal colors (`ansi0` … `ansi15`).
      '';
    };

    customColors = mkOption {
      type = types.attrsOf (types.strMatching "#?[0-9a-fA-F]{6}");
      default = { };
      example = { red = "#FF5555"; };
      description = ''
        Base hues for the terminal colors (`red`, `green`, `yellow`, `blue`,
        `magenta`, `cyan`). They are harmonized towards the seed color.
      '';
    };

    colors = mkOption {
      type = types.attrsOf types.str;
      readOnly = true;
      description = ''
        The generated palette (`primary`, `on_surface`, `ansi1`, …) for use in
        the rest of your configuration. Reading it uses import-from-derivation.
      '';
    };

    theme = mkOption {
      type = types.package;
      readOnly = true;
      description = "The rendered Nix-defined theme directory.";
    };

    dynamic = {
      enable = mkEnableOption ''
        runtime theming: `myt apply <wallpaper>` regenerates the palette and
        running terminals morph into it. The Nix-defined theme is the fallback'';

      wallpaper = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "~/.cache/current-wallpaper";
        description = ''
          A file (or symlink) to watch. Whenever it changes `myt apply` runs on it,
          so the terminal follows your wallpaper automatically.
        '';
      };

      hooks = mkOption {
        type = types.listOf types.str;
        default = [ ];
        example = [ "notify-send 'Material You' 'Terminal re-themed'" ];
        description = ''
          Shell commands run after each `myt apply`. `$MYT_THEME_DIR` and
          `$MYT_PALETTE` point at the new theme.
        '';
      };
    };

    animations = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = ''
          Smooth motion: kitty cursor trail, eased cursor blink, color morphing
          between palettes, the greeting ripple and staggered fastfetch reveal.
          Set `MYT_NO_ANIMATION=1` to disable it for a single session.
        '';
      };
      transitionMs = mkOption {
        type = types.ints.between 0 3000;
        default = 450;
        description = "Duration of the kitty color morph when the palette changes.";
      };
    };

    font = {
      name = mkOption {
        type = types.str;
        default = "RobotoMono Nerd Font";
        description = "Terminal font (a Nerd Font is needed for the prompt icons).";
      };
      package = mkOption {
        type = types.nullOr types.package;
        default = defaultFont;
        defaultText = literalExpression "pkgs.nerd-fonts.roboto-mono";
        description = "Package providing the font.";
      };
      size = mkOption {
        type = types.number;
        default = 12;
        description = "Font size in points.";
      };
    };

    kitty = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Theme kitty.";
      };
      opacity = mkOption {
        type = types.numbers.between 0 1;
        default = 0.94;
        description = "Background opacity.";
      };
      blur = mkOption {
        type = types.ints.unsigned;
        default = 32;
        description = "Background blur radius (where the compositor supports it).";
      };
      padding = mkOption {
        type = types.str;
        default = "10 14";
        description = "`window_padding_width` (vertical horizontal, in pt).";
      };
      lineHeight = mkOption {
        type = types.str;
        default = "108%";
        description = "Cell height, for a bit more breathing room between lines.";
      };
      remoteControl = mkOption {
        type = types.bool;
        default = true;
        description = ''
          Open a private remote-control socket (`socket-only`) so `myt` can
          morph the colors of running windows. Without it kitty picks up a new
          palette only after a restart.
        '';
      };
    };

    fish = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Theme fish (syntax highlighting, pager, greeting).";
      };
      greeting = mkOption {
        type = types.enum [ "both" "fastfetch" "ripple" "none" ];
        default = "both";
        description = "What a new shell shows: a ripple divider, fastfetch, both or nothing.";
      };
    };

    starship = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Material You chip-style starship prompt.";
      };
      transientPrompt = mkOption {
        type = types.bool;
        default = true;
        description = "Collapse previous prompts into a single `❯`.";
      };
      settings = mkOption {
        type = (pkgs.formats.toml { }).type;
        default = { };
        example = { time.disabled = true; directory.truncation_length = 5; };
        description = ''
          Merged over the built-in starship config. Palette roles such as
          `primary` or `tertiary_container` can be used as colors.
        '';
      };
    };

    fastfetch = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Material You fastfetch card.";
      };
      logo = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "nixos";
        description = ''
          Logo name or path. `null` shows the small logo of the detected
          distribution; `"nixos"` gives the big NixOS snowflake.
        '';
      };
      settings = mkOption {
        type = (pkgs.formats.json { }).type;
        default = { };
        description = ''
          Merged over the built-in fastfetch config. Strings may use
          `{{primary}}`-style placeholders for palette colors.
        '';
      };
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      programs.material-you-terminal = {
        inherit theme;
        colors = (lib.importJSON "${theme}/palette.json").colors;
      };

      home.packages = [ myt ] ++ lib.optional (cfg.font.package != null) cfg.font.package;
      fonts.fontconfig.enable = mkDefault true;

      xdg.configFile."material-you-terminal/config.json".text = builtins.toJSON runtimeConfig;

      # Re-render (dynamic mode) and morph running kitty windows into the new
      # palette after every `home-manager switch` / `nixos-rebuild switch`.
      home.activation.materialYouTerminal = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
        run ${lib.getExe myt} --config ${config.xdg.configHome}/material-you-terminal/config.json \
          refresh --quiet ${lib.optionalString (!cfg.kitty.enable) "--no-kitty"} || true
      '';
    }

    (mkIf cfg.kitty.enable {
      programs.kitty = {
        enable = true;
        font = mkDefault {
          inherit (cfg.font) name size;
          package = cfg.font.package;
        };
        settings = lib.mapAttrs (_: mkDefault) ({
          background_opacity = toString cfg.kitty.opacity;
          background_blur = cfg.kitty.blur;
          window_padding_width = cfg.kitty.padding;
          modify_font = "cell_height ${cfg.kitty.lineHeight}";

          cursor_shape = "beam";
          cursor_beam_thickness = "1.8";
          cursor_shape_unfocused = "hollow";
          cursor_blink_interval = if anim then "0.6 ease-in-out" else "0";
          cursor_stop_blinking_after = 15;
          cursor_trail = if anim then 3 else 0;
          cursor_trail_decay = "0.08 0.3";
          cursor_trail_start_threshold = 2;

          url_style = "curly";
          window_border_width = "1pt";
          draw_minimal_borders = true;
          inactive_text_alpha = "0.78";

          tab_bar_edge = "bottom";
          tab_bar_style = "powerline";
          tab_powerline_style = "round";
          tab_bar_align = "start";
          tab_bar_min_tabs = 2;
          tab_bar_margin_width = "6";
          tab_bar_margin_height = "4 4";
          tab_title_template = "{index}  {title}";
          active_tab_font_style = "bold";
          inactive_tab_font_style = "normal";

          scrollbar = "scrolled";
          scrollbar_width = "0.5";
          scrollbar_radius = "0.25";
          scrollbar_handle_opacity = "0.8";
          scrollbar_gap = "0.15";
        } // lib.optionalAttrs cfg.kitty.remoteControl {
          allow_remote_control = "socket-only";
          listen_on = "unix:\${XDG_RUNTIME_DIR}/kitty-myt-{kitty_pid}";
        });
        extraConfig = ''
          # material-you-terminal
          include ${themeDir}/kitty.conf
        '';
      };
    })

    (mkIf cfg.fish.enable {
      programs.fish = {
        enable = true;
        interactiveShellInit = lib.mkBefore ''
          # material-you-terminal
          set -g __myt_theme_dir ${themeDir}
          if test -r $__myt_theme_dir/colors.fish
              source $__myt_theme_dir/colors.fish
          end
          ${lib.optionalString cfg.starship.enable "set -gx STARSHIP_CONFIG $__myt_theme_dir/starship.toml"}
          ${lib.optionalString cfg.dynamic.enable ''
            # pick up `myt apply` in already running shells
            set -g __myt_colors_mtime (path mtime $__myt_theme_dir/colors.fish 2>/dev/null)
            function __myt_watch --on-event fish_prompt
                set -l m (path mtime $__myt_theme_dir/colors.fish 2>/dev/null)
                test "$m" = "$__myt_colors_mtime"; and return 1
                set -g __myt_colors_mtime $m
                source $__myt_theme_dir/colors.fish
            end
            function __myt_winch --on-signal WINCH
                __myt_watch; and commandline -f repaint
            end
          ''}
        '';
        functions = {
          fish_greeting = mkDefault {
            body = ''
              set -q MYT_NO_GREETING; and return
              ${greeting}
            '';
          };
        } // lib.optionalAttrs (cfg.starship.enable && cfg.starship.transientPrompt) {
          starship_transient_prompt_func = mkDefault {
            body = "starship module character";
          };
        };
      };
    })

    (mkIf cfg.starship.enable {
      programs.starship = {
        enable = true;
        enableFishIntegration = mkDefault cfg.fish.enable;
        enableTransience = mkDefault (cfg.fish.enable && cfg.starship.transientPrompt);
      };
    })

    (mkIf cfg.starship.enable {
      # Other shells (and starship's default STARSHIP_CONFIG) use the same config.
      xdg.configFile."starship.toml" = mkIf (config.programs.starship.settings == { }) (mkDefault {
        source = config.lib.file.mkOutOfStoreSymlink "${themeDir}/starship.toml";
      });
      warnings = lib.optional (config.programs.starship.settings != { }) ''
        material-you-terminal: with `programs.starship.settings` set, only fish uses the
        Material You prompt. Move your settings to `programs.material-you-terminal.starship.settings`.
      '';
    })

    (mkIf cfg.fastfetch.enable {
      home.packages = [ pkgs.fastfetch ];
      # Plain `fastfetch` uses the Material You card as well.
      xdg.configFile."fastfetch/config.jsonc" = mkDefault {
        source = config.lib.file.mkOutOfStoreSymlink "${themeDir}/fastfetch.jsonc";
      };
    })

    (mkIf (cfg.dynamic.enable && cfg.dynamic.wallpaper != null) {
      systemd.user.paths.material-you-terminal = {
        Unit.Description = "Re-theme the terminal when the wallpaper changes";
        Path.PathChanged = wallpaper;
        Install.WantedBy = [ "default.target" ];
      };
      systemd.user.services.material-you-terminal = {
        Unit.Description = "Apply Material You colors from the wallpaper";
        Service = {
          Type = "oneshot";
          ExecStart = "${lib.getExe myt} apply --quiet ${lib.escapeShellArg wallpaper}";
        };
      };
    })
  ]);
}
