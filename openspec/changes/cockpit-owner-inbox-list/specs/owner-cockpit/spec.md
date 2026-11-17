## MODIFIED Requirements

### Requirement: Owner item details
Each item SHALL show the pipeline name(s), the sender, the created and last-activity times, the title, the tags with a distinct `escalation` badge, `expects`, the body and the history of events, and the note "Answer here only if a short answer is enough; files to place or code to change must be handled outside the cockpit." The sender, `expects`, the times, the tags, the body, the history, the note and the answer controls SHALL be shown only while the item's line is open.

#### Scenario: Item card
- **WHEN** a pending item from `product` tagged `escalation` is listed and the owner opens its line
- **THEN** its details show the pipeline name, `product`, both times, the title, the `escalation` badge, `expects`, the body, the events and the note

#### Scenario: Details hidden until opened
- **WHEN** the Owner tab is loaded with a pending item that has a body, events and answer actions
- **THEN** its body, events and answer controls are not visible until the owner opens its line

## ADDED Requirements

### Requirement: Owner inbox line
In both the Pending and the Done section each owner item SHALL be shown as one compact line with its title (its ID when it has none), its arrival time (the handover's created time as date and time in the browser's local time zone) and its pipeline name(s). The order of the lines SHALL stay that of "Owner items list".

#### Scenario: Line per owner handover
- **WHEN** a hub has two pending handovers to `owner` for pipeline `alpha`, created at 09:05 and 10:40 UTC
- **THEN** the Pending section shows two lines, each with its title, its created date and time in local time and `alpha`

#### Scenario: Order kept
- **WHEN** an escalation's last activity is at 10:00 and a normal item's at 11:00
- **THEN** the normal item's line is listed first

### Requirement: Escalation marked in the list
A line whose item is tagged `escalation` SHALL carry the escalation mark on the line itself (the red left border and the `escalation` badge), visible without opening it. Lines of other items MUST NOT carry it.

#### Scenario: Escalation line marked
- **WHEN** the Owner tab lists one escalation and two normal owner handovers
- **THEN** only the escalation's line shows the red mark and the `escalation` badge

### Requirement: Opening and closing an owner line
Clicking a line, or pressing Enter or Space while it has keyboard focus, SHALL open the item's details in place below the line; doing it again SHALL close them. At most one item SHALL be open at a time: opening a line closes the one open before. Each line SHALL be reachable with the keyboard and SHALL expose whether it is open.

#### Scenario: Open shows the details
- **WHEN** the owner clicks the line of a pending item that expects `response`
- **THEN** its body, its history of events and its answer controls (text field and the allowed actions) are shown

#### Scenario: Keyboard
- **WHEN** a line has keyboard focus and the owner presses Enter, then Space
- **THEN** the details open, then close

#### Scenario: One open at a time
- **WHEN** one item is open and the owner opens another line
- **THEN** the second item's details are shown and the first item's are hidden

### Requirement: Owner list state kept across refresh
A refresh (periodic or the "Refresh" button) SHALL keep the open item open when it is still listed, and MUST NOT lose or clear an answer being typed, whether its item is open or closed. After an answer is sent successfully the list SHALL be reloaded as today.

#### Scenario: Open item and typed answer survive a refresh
- **WHEN** the owner opens a pending item, types part of an answer and the page refreshes
- **THEN** the item is still open and the text field still holds the typed text

#### Scenario: Open item no longer listed
- **WHEN** the open item has disappeared from the hub's list at the next refresh
- **THEN** the page shows the remaining lines, all closed, without an error
