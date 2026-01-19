; Inno Setup Script for Gym Management System

#define MyAppName "Gym Management System"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Gym System"
#define MyAppURL "https://gymsystem.pythonanywhere.com"
#define MyAppExeName "GymSystem.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={pf}\GymSystem
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=GymSystem_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\GymSystem.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config_template.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Gym Management System"; Flags: nowait postinstall skipifsilent
