import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    signal closeRequested()
    Keys.onEscapePressed: closeRequested()
    property var teams: []
    property var saved: ({})
    property bool loaded: false
    property int revision: 0
    ListModel { id: subscriptions }
    property string message: ""
    property bool failed: false
    property string snapshot: ""
    property string payload: ""
    property string operation: ""
    readonly property bool busy: backend.running
    readonly property string draft: { revision; return JSON.stringify({sender: sender.text, displayName: displayName.text, subscriptions: subscriptionData()}) }
    function subscriptionData() {
        var rows = []
        for (var i = 0; i < subscriptions.count; i++) {
            var row = subscriptions.get(i)
            rows.push({id: row.subscriptionId, recipient: row.recipient, team: row.team, enabled: row.active})
        }
        return rows
    }
    function edit(index, role, value) { subscriptions.setProperty(index, role, value); revision++ }
    function addSubscription() {
        subscriptions.append({subscriptionId: "sub-" + Date.now() + "-" + Math.floor(Math.random()*1000000), recipient: "", team: "", active: false, status: "Save this subscription to get started.", lastCheck: 0, lastSent: 0, workerError: ""})
        revision++
    }
    readonly property bool dirty: snapshot !== draft || appPassword.text !== ""
    readonly property var teamOptions: [{value: "", label: "Choose a team"}].concat(teams.slice().sort(function(a, b) {
        return a.name.localeCompare(b.name)
    }).map(function(team) { return {value: team.code, label: team.name} }))

    function clearSecrets() { appPassword.text = "" }

    function request(action, subscriptionId) {
        if (busy) return
        operation = action
        failed = false
        message = action === "test" ? "Sending test email…" : action === "save" ? "Saving settings…" : "Loading settings…"
        var data = {action: action, subscriptionId: subscriptionId || ""}
        if (action === "save") {
            data = JSON.parse(draft)
            data.action = action
            data.password = appPassword.text
        }
        payload = JSON.stringify(data)
        backend.running = true
    }

    function applySettings(data) {
        saved = data
        sender.text = data.sender || ""
        displayName.text = data.displayName || "The Rathole"
        subscriptions.clear()
        var rows = data.subscriptions || []
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i]
            subscriptions.append({subscriptionId: row.id, recipient: row.recipient, team: row.team, active: row.enabled, status: row.status || "", lastCheck: row.lastCheck || 0, lastSent: row.lastSent || 0, workerError: row.workerError || ""})
        }
        revision++
        clearSecrets()
        snapshot = draft
        loaded = true
    }

    function friendlyTime(epoch) {
        return epoch ? Qt.formatDateTime(new Date(epoch * 1000), "MMM d, h:mm AP") : "Not yet"
    }

    Process {
        id: backend
        command: ["python3", "-B", decodeURIComponent(Qt.resolvedUrl("notifications.py").toString().replace(/^file:\/\//, ""))]
        stdinEnabled: true
        onStarted: {
            write(root.payload + "\n")
            root.payload = ""
        }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var response = JSON.parse(text)
                    root.failed = response.ok !== true
                    if (response.settings) root.applySettings(response.settings)
                    root.message = response.message || ""
                } catch (error) {
                    root.failed = true
                    root.message = "Could not read notification settings."
                }
            }
        }
        onExited: function(exitCode, exitStatus) {
            root.payload = ""
            if (exitCode !== 0 && root.message === "Loading settings…") {
                root.failed = true
                root.message = "Could not load notification settings."
            }
        }
    }

    Component.onCompleted: request("get")
    Component.onDestruction: {
        payload = ""
        backend.running = false
    }

    Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: form.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar {}

        Column {
            id: form
            width: scroll.width - Style.space(12)
            spacing: Style.space(16)

            Text {
                text: "Game result emails"
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.space(17)
                font.bold: true
            }
            Text {
                width: parent.width
                text: "Get a short recap after your team's game finishes. Checks run every five minutes while you're signed in."
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.space(11)
                wrapMode: Text.WordWrap
            }

            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: Style.space(28)
                rowSpacing: Style.space(16)
                enabled: !root.busy
                EmailField {
                    id: sender
                    Layout.fillWidth: true
                    Layout.preferredWidth: (parent.width - parent.columnSpacing) / 2
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignTop
                    label: "Sender email (Gmail)"
                    placeholderText: "you@gmail.com"
                }
                EmailField {
                    id: displayName
                    Layout.fillWidth: true
                    Layout.preferredWidth: (parent.width - parent.columnSpacing) / 2
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignTop
                    label: "Sender display name"
                    text: "The Rathole"
                }
                EmailField {
                    id: appPassword
                    Layout.fillWidth: true
                    Layout.preferredWidth: (parent.width - parent.columnSpacing) / 2
                    Layout.minimumWidth: 0
                    Layout.alignment: Qt.AlignTop
                    label: "Gmail app password"
                    password: true
                    placeholderText: root.saved.hasPassword && sender.text.trim() === root.saved.sender ? "Saved in keyring · leave blank to keep" : "Google's 16-character app password"
                    hint: "Stored in your system keyring. Your normal Gmail password won't work."
                }
            }

            Text {
                text: "Create a Gmail app password ↗"
                color: Color.accent
                font.family: Style.font.family
                font.pixelSize: Style.space(11)
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.openUrlExternally("https://myaccount.google.com/apppasswords")
                }
            }

            Row {
                spacing: Style.space(12)
                Ui.Button {
                    text: root.busy && root.operation === "save" ? "Saving…" : "Save settings"
                    bordered: true
                    enabled: root.loaded && !root.busy
                    focusable: true
                    onClicked: root.request("save")
                }
                Ui.Button {
                    text: "Refresh status"
                    enabled: !root.busy && !root.dirty
                    focusable: true
                    onClicked: root.request("get")
                }
            }
            Text {
                width: parent.width
                visible: root.message !== "" || root.dirty
                text: root.message || (root.dirty ? "Save changes before sending a test email." : "")
                color: root.failed ? Color.urgent : Color.accent
                font.family: Style.font.family
                font.pixelSize: Style.space(11)
                wrapMode: Text.WordWrap
            }
            Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.12) }
            Row {
                spacing: Style.space(16)
                Text { text: "Recipient subscriptions"; color: Color.foreground; font.bold: true; font.family: Style.font.family; font.pixelSize: Style.space(14) }
                Ui.Button { text: "+ Add recipient / team"; enabled: root.loaded && !root.busy; onClicked: root.addSubscription() }
            }
            Repeater {
                model: subscriptions
                delegate: Column {
                    id: subscriptionRow
                    required property int index
                    required property string subscriptionId
                    required property string recipient
                    required property string team
                    required property bool active
                    required property string status
                    required property double lastCheck
                    required property double lastSent
                    required property string workerError
                    width: form.width
                    spacing: Style.space(10)
                    GridLayout {
                        width: parent.width
                        columns: 4
                        columnSpacing: Style.space(16)
                        enabled: !root.busy
                        EmailField {
                            Layout.fillWidth: true
                            Layout.preferredWidth: parent.width * 0.36
                            Layout.minimumWidth: 0
                            label: "Send to"
                            text: subscriptionRow.recipient
                            placeholderText: "recipient@example.com"
                            onEdited: function(value) { root.edit(subscriptionRow.index, "recipient", value) }
                        }
                        Column {
                            Layout.fillWidth: true
                            Layout.preferredWidth: parent.width * 0.32
                            spacing: Style.space(6)
                            Text { text: "Team"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.space(12) }
                            Ui.Dropdown {
                                width: parent.width
                                showLabel: false
                                options: root.teamOptions
                                value: subscriptionRow.team
                                onChanged: function(value) { root.edit(subscriptionRow.index, "team", value) }
                            }
                        }
                        Column {
                            spacing: Style.space(10)
                            Text { text: subscriptionRow.active ? "On" : "Off"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.space(12) }
                            Ui.ToggleSwitch { checked: subscriptionRow.active; onToggled: root.edit(subscriptionRow.index, "active", !subscriptionRow.active) }
                        }
                        Row {
                            spacing: Style.space(8)
                            Ui.Button {
                                text: "Send test"
                                bordered: true
                                enabled: root.loaded && !root.busy && !root.dirty && root.saved.hasPassword && !!root.saved.sender && !!subscriptionRow.recipient && !!subscriptionRow.team
                                tooltipText: "Send this team's latest result and next scheduled game"
                                onClicked: root.request("test", subscriptionRow.subscriptionId)
                            }
                            Ui.Button { text: "×"; tooltipText: "Remove subscription"; onClicked: { subscriptions.remove(subscriptionRow.index); root.revision++ } }
                        }
                    }
                    Text {
                        width: parent.width
                        text: subscriptionRow.status + " · Last check: " + root.friendlyTime(subscriptionRow.lastCheck) + " · Last email: " + root.friendlyTime(subscriptionRow.lastSent)
                        color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.space(10); wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width; visible: subscriptionRow.workerError !== ""; text: subscriptionRow.workerError
                        color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.space(10); wrapMode: Text.WordWrap
                    }
                    Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.12) }
                }
            }
            Text {
                width: parent.width
                text: "Each enabled recipient/team subscription gets future results. Add another row to follow a different team at the same address. Save changes before testing."
                color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.space(10); wrapMode: Text.WordWrap
            }
            Text {
                width: parent.width
                visible: !!root.saved.keyringError
                text: root.saved.keyringError || ""
                color: Color.urgent
                font.family: Style.font.family
                font.pixelSize: Style.space(11)
                wrapMode: Text.WordWrap
            }
        }
    }
}
