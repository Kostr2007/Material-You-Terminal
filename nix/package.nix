{ lib
, stdenvNoCC
, makeWrapper
, python3
, matugen
, procps
}:

let
  python = python3.withPackages (ps: [ ps.pillow ]);
in
stdenvNoCC.mkDerivation {
  pname = "material-you-terminal";
  version = "1.1.0";

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [ ../cli ../templates ];
  };

  nativeBuildInputs = [ makeWrapper ];

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    install -Dm644 cli/myt.py $out/libexec/myt.py
    install -Dm644 cli/myt_logo.py $out/libexec/myt_logo.py
    cp -r cli/assets $out/libexec/assets
    mkdir -p $out/share/material-you-terminal
    cp -r templates $out/share/material-you-terminal/templates
    makeWrapper ${python.interpreter} $out/bin/myt \
      --add-flags $out/libexec/myt.py \
      --prefix PATH : ${lib.makeBinPath [ matugen procps ]}
    runHook postInstall
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    $out/bin/myt --version
  '';

  meta = {
    description = "Material You theming for kitty, fish, starship and fastfetch";
    license = [ lib.licenses.mit lib.licenses.cc-by-40 ];
    mainProgram = "myt";
    platforms = lib.platforms.unix;
  };
}
