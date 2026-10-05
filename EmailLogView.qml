import QtQuick
import QtQuick.Controls as Controls
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    signal closeRequested()
    Keys.onEscapePressed: closeRequested()
    property var entries: []
    property string message: ""
    property string action: "log"
    readonly property bool busy: backend.running
    function request(value) {
        if (busy) return
        action = value
        message = ""
        backend.running = true
    }
    Process {
        id: backend
        command: ["python3", "-B", decodeURIComponent(Qt.resolvedUrl("notifications.py").toString().replace(/^file:\/\//, ""))]
        stdinEnabled: true
        onStarted: write(JSON.stringify({action: root.action}) + "\n")
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var response = JSON.parse(text)
                    if (response.ok) root.entries = response.entries || []
                    else root.message = response.message || "Could not read the email log."
                } catch (error) { root.message = "Could not read the email log." }
            }
        }
    }
    Column {
        id: heading
        width: parent.width
        spacing: Style.space(10)
        Row {
            spacing: Style.space(16)
            Text { text: "Email log"; color: Color.foreground; font.bold: true; font.family: Style.font.family; font.pixelSize: Style.space(17) }
            Ui.Button { text: "Refresh log"; enabled: !root.busy; onClicked: root.request("log") }
            Ui.Button { text: "Clear log"; enabled: !root.busy && root.entries.length > 0; onClicked: root.request("clear-log") }
        }
        Text {
            width: parent.width
            text: "Test and automatic emails · Kept for 7 days · Sent means accepted by Gmail."
            color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.space(11); wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            visible: root.busy || root.message !== "" || root.entries.length === 0
            text: root.busy ? "Loading…" : root.message || "No emails logged yet. New email attempts will appear here."
            color: root.message ? Color.urgent : Color.muted
            font.family: Style.font.family; font.pixelSize: Style.space(11); wrapMode: Text.WordWrap
        }
    }
    Flickable {
        anchors.top: heading.bottom
        anchors.topMargin: Style.space(16)
        anchors.bottom: parent.bottom
        width: parent.width
        contentWidth: width
        contentHeight: rows.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        Column {
            id: rows
            width: parent.width - Style.space(12)
            spacing: Style.space(14)
            Repeater {
                model: root.entries
                delegate: Column {
                    required property var modelData
                    width: rows.width
                    spacing: Style.space(5)
                    Text {
                        width: parent.width
                        text: Qt.formatDateTime(new Date(parent.modelData.time * 1000), "MMM d, yyyy · h:mm AP") + " · " + parent.modelData.kind + " · " + parent.modelData.status
                        color: parent.modelData.status === "Sent" ? Color.accent : Color.urgent
                        font.family: Style.font.family; font.pixelSize: Style.space(11); wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: parent.modelData.team + " → " + parent.modelData.recipient + "\n" + parent.modelData.subject
                        color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.space(12); wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: parent.modelData.detail
                        color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.space(10); wrapMode: Text.WordWrap
                    }
                    Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.12) }
                }
            }
        }
    }
}
