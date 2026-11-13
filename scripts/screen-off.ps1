# Darkens the screen for the night without starting standby (harness-survive-sleep D2).
# A borderless black window covers every monitor and hides the cursor; any key press or mouse move closes it.
# The power plan's display timeout then turns the panel off as an idle display-off, which does not start
# Modern Standby while the dispatcher keeps the computer awake. (Turning the monitor off with SC_MONITORPOWER
# is handled like the power button on Modern Standby: the computer enters standby, whatever keeps it awake.)
Start-Sleep -Seconds 1  # let the Enter key release so it does not close the window at once
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = 'None'
$form.StartPosition = 'Manual'
$form.Bounds = $bounds
$form.BackColor = [System.Drawing.Color]::Black
$form.TopMost = $true
$form.ShowInTaskbar = $false
$form.KeyPreview = $true
$form.Text = 'screen-off'

$script:start = $null
$close = { $form.Close() }
$form.Add_KeyDown($close)
$form.Add_MouseDown($close)
$form.Add_MouseMove({
    $p = [System.Windows.Forms.Cursor]::Position
    if ($null -eq $script:start) { $script:start = $p; return }
    if ([Math]::Abs($p.X - $script:start.X) -gt 3 -or [Math]::Abs($p.Y - $script:start.Y) -gt 3) { $form.Close() }
})
$form.Add_Shown({ [System.Windows.Forms.Cursor]::Hide(); $form.Activate() })
$form.Add_FormClosed({ [System.Windows.Forms.Cursor]::Show() })

Write-Output "Screen darkened by a black window (no standby); the display timeout turns the panel off. Press a key or move the mouse to bring it back."
[System.Windows.Forms.Application]::Run($form)
Write-Output "Screen back."
