Unicode true
!include "LogicLib.nsh"
!include "x64.nsh"
!include "MUI2.nsh"
Name "Kurt Launcher ${VERSION}"
OutFile "${OUTPUT}"
Icon "${PAYLOAD}\assets\icon.ico"
RequestExecutionLevel user
CRCCheck force
SetCompressor zlib
ShowInstDetails show
AutoCloseWindow true
BrandingText "Kurt Launcher"
Caption "Kurt Launcher kurulumu"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "Kurt Launcher 64 bit Windows gerektirir." /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
FunctionEnd

Section "Kurt Launcher"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR\KurtLauncher"
  DetailPrint "Uygulama dosyaları hazırlanıyor..."
  File /r "${PAYLOAD}\*.*"
  ; A background install worker must not keep the disposable payload directory open.
  SetOutPath "$TEMP"
  System::Call 'kernel32::SetEnvironmentVariableW(w "PYINSTALLER_RESET_ENVIRONMENT", w "1")i.r0'
  DetailPrint "Kurt Launcher kuruluyor ve açılışı doğrulanıyor..."
  ClearErrors
  ExecWait '"$PLUGINSDIR\KurtLauncher\KurtLauncher.exe" --setup-receipt "$PLUGINSDIR\KurtLauncher\setup-receipt.txt"' $0
  IfErrors failed
  IntCmp $0 0 +2
    Goto failed
  FileOpen $1 "$PLUGINSDIR\KurtLauncher\setup-receipt.txt" r
  IfErrors failed
  FileReadUTF16LE $1 $2
  FileClose $1
  StrCpy $2 $2 -2
  StrCmp $2 "ALREADY_OPEN" already_open
  StrCmp $2 "" failed
  StrCpy $3 0
wait_result:
  IfFileExists "$2" read_result
  Sleep 200
  IntOp $3 $3 + 1
  IntCmp $3 900 failed wait_result failed
read_result:
  FileOpen $1 "$2" r
  IfErrors failed
  FileReadByte $1 $4
  FileReadByte $1 $5
  FileReadByte $1 $6
  ${If} $4 != 239
  ${OrIf} $5 != 187
  ${OrIf} $6 != 191
    FileSeek $1 0 SET
  ${EndIf}
  FileRead $1 $4
  FileClose $1
  StrCpy $4 $4 9
  StrCmp $4 "Update OK" done failed
already_open:
  DetailPrint "Kurt Launcher zaten açık. Yeni sürüm uygulama üzerinden otomatik alınacak."
  Goto done
failed:
  ReadEnvStr $7 "KURT_SETUP_LOG"
  StrCmp $7 "" +4
    FileOpen $8 "$7" w
    FileWrite $8 "Child exit: $0; result path: $2; result prefix: $4$\r$\n"
    FileClose $8
  SetErrorLevel 1
  MessageBox MB_OK|MB_ICONSTOP "Kurulum tamamlanamadı. Kurt Launcher kapalıyken yeniden deneyin. Günlük: $2" /SD IDOK
  Abort
done:
  DetailPrint "Kurulum tamamlandı. Oyunlar ortak veri klasöründe saklanır."
  SetErrorLevel 0
SectionEnd
