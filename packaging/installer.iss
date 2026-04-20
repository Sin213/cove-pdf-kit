; Inno Setup script for Cove PDF Kit (Windows)
; Invoked from build.ps1 via:
;   iscc /DAppVersion=X.Y.Z /DSourceDir=<abs dist\cove-pdf-kit> \
;        /DOutputDir=<abs release> /DIconFile=<abs cove_icon.ico> installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\cove-pdf-kit"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif
#ifndef IconFile
  #define IconFile "..\cove_icon.ico"
#endif

[Setup]
AppId={{C8D2A591-4E63-4B27-9F1A-2D5E8F8C3B40}
AppName=Cove PDF Kit
AppVersion={#AppVersion}
AppPublisher=Cove
AppPublisherURL=https://github.com/Sin213/cove-pdf-kit
AppSupportURL=https://github.com/Sin213/cove-pdf-kit/issues
AppUpdatesURL=https://github.com/Sin213/cove-pdf-kit/releases
DefaultDirName={autopf}\Cove PDF Kit
DefaultGroupName=Cove PDF Kit
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\cove-pdf-kit.exe
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=cove-pdf-kit-{#AppVersion}-Setup
SetupIconFile={#IconFile}
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cove PDF Kit"; Filename: "{app}\cove-pdf-kit.exe"
Name: "{group}\Uninstall Cove PDF Kit"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cove PDF Kit"; Filename: "{app}\cove-pdf-kit.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\cove-pdf-kit.exe"; Description: "Launch Cove PDF Kit"; Flags: nowait postinstall skipifsilent
