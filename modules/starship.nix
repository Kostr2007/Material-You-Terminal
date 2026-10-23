# Starship prompt in Material You style: every module is a rounded "chip"
# (Material 3 assist chips) using the palette roles defined in
# `[palettes.material_you]`, which material-you-terminal appends at build time.
{ lib }:

let
  L = "";
  R = "";

  # [ content ] as a pill with the given container / on-container roles.
  chip = bg: fg: content: "[${L}](fg:${bg})[${content}](bg:${bg} fg:${fg})[${R}](fg:${bg})";

  lang = symbol: {
    inherit symbol;
    format = "${chip "surface_container_highest" "tertiary" "$symbol($version)"} ";
    version_format = "\${raw}";
  };

  languages = {
    python = lang " " // {
      format = "${chip "surface_container_highest" "tertiary" "$symbol($version)( \\($virtualenv\\))"} ";
    };
    nodejs = lang " ";
    bun = lang " ";
    deno = lang " ";
    rust = lang " ";
    golang = lang " ";
    c = lang " ";
    cpp = lang " ";
    java = lang " ";
    kotlin = lang " ";
    lua = lang " ";
    zig = lang " ";
    php = lang " ";
    ruby = lang " ";
    dart = lang " ";
    haskell = lang " ";
    elixir = lang " ";
    nim = lang " ";
  };
in
{
  "$schema" = "https://starship.rs/config-schema.json";
  palette = "material_you";
  add_newline = true;
  continuation_prompt = "[∙](fg:outline) ";

  format = lib.concatStrings ([
    "$os"
    "$directory"
    "$git_branch"
    "$git_state"
    "$git_status"
    "$nix_shell"
    "$direnv"
    "$docker_context"
  ] ++ map (n: "$" + n) (builtins.attrNames languages) ++ [
    "$fill"
    "$cmd_duration"
    "$status"
    "$jobs"
    "$username"
    "$hostname"
    "$time"
    "$line_break"
    "$character"
  ]);

  fill.symbol = " ";

  os = {
    disabled = false;
    format = "${chip "primary" "on_primary" "$symbol"} ";
    symbols = {
      NixOS = "";
      Arch = "";
      Debian = "";
      Fedora = "";
      Ubuntu = "";
      Linux = "";
      Macos = "";
      Windows = "";
      Unknown = "";
    };
  };

  directory = {
    format = "${chip "primary_container" "on_primary_container" "󰉋 $path$read_only"} ";
    read_only = " 󰌾";
    truncation_length = 3;
    truncation_symbol = "…/";
    truncate_to_repo = true;
    home_symbol = "~";
  };

  git_branch = {
    symbol = " ";
    format = "${chip "secondary_container" "on_secondary_container" "$symbol$branch(:$remote_branch)"} ";
  };

  git_state.format = "(${chip "error_container" "on_error_container" "$state( $progress_current/$progress_total)"} )";

  git_status = {
    format = "(${chip "tertiary_container" "on_tertiary_container" "$all_status$ahead_behind "} )";
    conflicted = " =\${count}";
    ahead = " ⇡\${count}";
    behind = " ⇣\${count}";
    diverged = " ⇡\${ahead_count}⇣\${behind_count}";
    up_to_date = "";
    untracked = " ?\${count}";
    stashed = " ≡\${count}";
    modified = " !\${count}";
    staged = " +\${count}";
    renamed = " »\${count}";
    deleted = " ✘\${count}";
  };

  nix_shell = {
    symbol = " ";
    format = "${chip "tertiary_container" "on_tertiary_container" "$symbol$state( $name)"} ";
    impure_msg = "impure";
    pure_msg = "pure";
    unknown_msg = "shell";
  };

  direnv = {
    disabled = false;
    format = "(${chip "surface_container_highest" "on_surface_variant" "$symbol$loaded"} )";
    symbol = "󰈙 ";
    loaded_msg = "";
    unloaded_msg = "off";
    allowed_msg = "";
    not_allowed_msg = "!";
    denied_msg = "✘";
  };

  docker_context = {
    symbol = " ";
    format = "${chip "surface_container_highest" "tertiary" "$symbol$context"} ";
  };

  cmd_duration = {
    min_time = 2000;
    format = "${chip "surface_container_high" "on_surface_variant" "󰔟 $duration"} ";
    show_notifications = false;
  };

  status = {
    disabled = false;
    symbol = "✕ ";
    format = "${chip "error_container" "on_error_container" "$symbol$status"} ";
    map_symbol = false;
    pipestatus = false;
  };

  jobs = {
    symbol = "✦ ";
    number_threshold = 1;
    format = "${chip "secondary_container" "on_secondary_container" "$symbol$number"} ";
  };

  username = {
    show_always = false;
    format = "${chip "tertiary_container" "on_tertiary_container" " $user"} ";
  };

  hostname = {
    ssh_only = true;
    ssh_symbol = "󰣀 ";
    format = "${chip "tertiary_container" "on_tertiary_container" "$ssh_symbol$hostname"} ";
  };

  time = {
    disabled = false;
    time_format = "%H:%M";
    format = chip "primary" "on_primary" "󰥔 $time";
  };

  character = {
    success_symbol = "[❯](bold fg:primary)";
    error_symbol = "[❯](bold fg:error)";
    vimcmd_symbol = "[❮](bold fg:tertiary)";
    vimcmd_replace_one_symbol = "[❮](bold fg:secondary)";
    vimcmd_replace_symbol = "[❮](bold fg:secondary)";
    vimcmd_visual_symbol = "[❮](bold fg:primary)";
  };
}
  // languages
