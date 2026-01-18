; Inno Setup Script for Gym Management System
; This creates a professional Windows installer

#define MyAppName "Gym Management System"
#define MyAppNameArabic "نظام إدارة الجيم"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Gym System"
#define MyAppURL "https://gymsystem.pythonanywhere.com"
#define MyAppExeName "GymSystem.exe"

[Setup]
; Application info
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation settings
DefaultDirName={autopf}\GymSystem
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=..\dist\installer
OutputBaseFilename=GymSystem_Setup_{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Compression
Compression=lzma2/max
SolidCompression=yes

; UI settings
WizardStyle=modern
WizardSizePercent=120

; Privileges (install for current user or all users)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Languages
; Note: Arabic language file may need to be downloaded separately
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checked
Name: "quicklaunchicon"; Description: "Create a Quick Launch shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Main executable
Source: "..\dist\GymSystem.exe"; DestDir: "{app}"; Flags: ignoreversion

; Assets folder
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; Config file template
Source: "..\config_template.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist

[Icons]
; Start Menu shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppNameArabic}"

; Desktop shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppNameArabic}"

; Quick Launch shortcut
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; Option to run after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Gym Management System"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up config and logs on uninstall (optional)
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\*.log"
Type: dirifempty; Name: "{app}"

[Code]
// Custom code for installation

procedure InitializeWizard;
begin
  // You can customize the wizard here
  WizardForm.WelcomeLabel2.Caption :=
    'This will install Gym Management System on your computer.' + #13#10 + #13#10 +
    'سيقوم هذا البرنامج بتثبيت نظام إدارة الجيم على جهاز الكمبيوتر الخاص بك.' + #13#10 + #13#10 +
    'Click Next to continue, or Cancel to exit Setup.';
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;
