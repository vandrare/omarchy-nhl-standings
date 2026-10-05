import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "local.nhl-standings"
    manageIpc: false
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    property string conference: "Western"
    property string page: "standings"
    property var teams: []
    property string dataDate: ""
    property string standingsError: ""
    property bool stale: false
    property double updated: 0
    property var selectedTeam: null
    property var game: null
    property string gameError: ""
    property bool gameStale: false
    property string pendingTeam: ""
    property int cursorIndex: -1
    readonly property var divisionNames: conference === "Western" ? ["Central", "Pacific"] : ["Atlantic", "Metropolitan"]
    readonly property var conferenceTeams: divisionTeams(divisionNames[0]).concat(divisionTeams(divisionNames[1]))

    function divisionTeams(name) {
        return teams.filter(function(t) { return t.conference === root.conference && t.division === name })
            .sort(function(a, b) { return a.divisionRank - b.divisionRank || b.pts - a.pts })
    }

    readonly property string script: Qt.resolvedUrl("nhl.py").toString().replace(/^file:\/\//, "")

    function refresh(force) {
        if (standingsProcess.running) return
        standingsProcess.command = ["python3", decodeURIComponent(script), "standings"]
        if (force === true) standingsProcess.command = standingsProcess.command.concat(["--force"])
        standingsProcess.running = true
    }

    function open() {
        page = "standings"
        notificationSettings.clearSecrets()
        conference = "Western"
        selectedTeam = null
        cursorIndex = -1
        controller.show()
        refresh(false)
    }

    function close() {
        notificationSettings.clearSecrets()
        controller.hide()
    }

    function chooseTab(value) {
        if (value === "Settings") {
            page = "settings"
            if (!notificationSettings.dirty) notificationSettings.request("get")
            Qt.callLater(function() { notificationSettings.forceActiveFocus() })
        } else if (value === "Log") {
            notificationSettings.clearSecrets()
            page = "log"
            emailLog.request("log")
            Qt.callLater(function() { emailLog.forceActiveFocus() })
        } else {
            notificationSettings.clearSecrets()
            page = "standings"
            chooseConference(value)
            Qt.callLater(function() { keys.forceActiveFocus() })
        }
    }

    function chooseConference(value) {
        conference = value
        selectedTeam = null
        cursorIndex = -1
    }

    function selectTeam(team) {
        selectedTeam = team
        game = null
        gameError = ""
        gameStale = false
        pendingTeam = team.code
        fetchSchedule()
    }

    function fetchSchedule() {
        if (scheduleProcess.running || pendingTeam === "") return
        var code = pendingTeam
        pendingTeam = ""
        scheduleProcess.command = ["python3", decodeURIComponent(script), "schedule", code]
        scheduleProcess.running = true
    }

    function formatGameTime() {
        if (!game) return ""
        var date = new Date(game.start)
        return Qt.formatDateTime(date, "ddd, MMM d, yyyy") + " · "
            + (game.timeTbd ? "Time TBD" : Qt.formatDateTime(date, "h:mm AP t"))
    }

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        tooltipText: "NHL standings"
        slotSize: Style.space(38)
        iconComponent: Component {
            Text {
                text: "NHL"
                color: root.barForeground
                font.family: Style.font.family
                font.pixelSize: Style.space(12)
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
        onPressed: function(b) {
            if (b === Qt.MiddleButton) root.refresh(true)
            else root.toggle()
        }
    }

    Process {
        id: standingsProcess
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    root.standingsError = result.error || ""
                    if (result.teams) {
                        root.teams = result.teams
                        root.dataDate = result.date || ""
                        root.updated = result.updated || 0
                        root.stale = result.stale === true
                    }
                } catch (e) { root.standingsError = "Could not read NHL standings." }
            }
        }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0) root.standingsError = "Could not load NHL standings."
        }
    }

    Process {
        id: scheduleProcess
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    if (!root.selectedTeam || result.team !== root.selectedTeam.code) return
                    root.game = result.game || null
                    root.gameError = result.error || ""
                    root.gameStale = result.stale === true
                } catch (e) { root.gameError = "Could not read the team schedule." }
            }
        }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0 && root.pendingTeam === "") root.gameError = "Could not load the team schedule."
            Qt.callLater(root.fetchSchedule)
        }
    }

    Timer {
        interval: 900000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh(false)
    }

    KeyboardPanel {
        id: panel
        anchorItem: button
        bar: root.bar
        owner: root
        open: root.opened
        focusTarget: root.page === "settings" ? notificationSettings : root.page === "log" ? emailLog : keys
        contentWidth: fittedContentWidth(Style.space(1040))
        contentHeight: fittedContentHeight(Style.space(560))

        PanelKeyCatcher {
            id: keys
            anchors.fill: parent
            blocked: root.page !== "standings"
            onCloseRequested: root.close()
            onTabRequested: function(direction) { root.switchPanel(direction) }
            onMoveRequested: function(dx, dy) {
                if (dx) root.chooseConference(dx < 0 ? "Western" : "Eastern")
                if (dy && root.conferenceTeams.length) {
                    root.cursorIndex = Math.max(0, Math.min(root.conferenceTeams.length - 1, root.cursorIndex + dy))
                    var firstCount = root.divisionTeams(root.divisionNames[0]).length
                    var column = root.cursorIndex < firstCount ? 0 : 1
                    var table = divisionRepeater.itemAt(column)
                    if (table) table.ensureVisible(root.cursorIndex - (column === 0 ? 0 : firstCount))
                }
            }
            onActivateRequested: {
                if (root.cursorIndex >= 0) root.selectTeam(root.conferenceTeams[root.cursorIndex])
            }
            onTextKey: function(text) {
                if (text.toLowerCase() === "r") root.refresh(true)
                else if (text.toLowerCase() === "s") root.chooseTab("Settings")
                else if (text.toLowerCase() === "l") root.chooseTab("Log")
            }

            Column {
                id: header
                width: parent.width
                spacing: Style.space(12)
                Row {
                    width: parent.width
                    Text {
                        width: parent.width - headerActions.implicitWidth
                        text: "NHL standings"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.space(20)
                        font.bold: true
                    }
                    Row {
                        id: headerActions
                        spacing: Style.space(4)
                        PanelActionButton {
                            iconText: "⚙"
                            tooltipText: "Settings"
                            foreground: root.page === "settings" ? Color.accent : Color.foreground
                            onClicked: root.chooseTab("Settings")
                        }
                        PanelActionButton {
                            iconText: "≡"
                            tooltipText: "Email log"
                            foreground: root.page === "log" ? Color.accent : Color.foreground
                            onClicked: root.chooseTab("Log")
                        }
                        PanelActionButton {
                            iconText: "↻"
                            tooltipText: "Refresh standings"
                            visible: root.page === "standings"
                            enabled: !standingsProcess.running
                            onClicked: root.refresh(true)
                        }
                        PanelActionButton {
                            iconText: "×"
                            tooltipText: "Close"
                            onClicked: root.close()
                        }
                    }
                }
                Row {
                    width: parent.width
                    spacing: Style.space(8)
                    Repeater {
                        model: ["Western", "Eastern"]
                        delegate: Rectangle {
                            required property string modelData
                            readonly property bool selectedTab: root.page === "standings" && root.conference === modelData
                            width: (header.width - Style.space(8)) / 2
                            height: Style.space(36)
                            radius: Style.space(6)
                            color: selectedTab ? Util.alpha(Color.accent, 0.18) : (tabMouse.containsMouse ? Util.alpha(Color.foreground, 0.06) : "transparent")
                            Text {
                                anchors.centerIn: parent
                                text: parent.modelData + " Conference"
                                color: parent.selectedTab ? Color.accent : Color.muted
                                font.family: Style.font.family
                                font.pixelSize: Style.space(13)
                                font.bold: parent.selectedTab
                            }
                            MouseArea {
                                id: tabMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.chooseTab(parent.modelData)
                            }
                        }
                    }
                }
                Text {
                    width: parent.width
                    visible: root.page === "standings"
                    text: root.standingsError || (root.stale ? "Offline · showing cached standings" : (standingsProcess.running ? "Updating…" : "Standings as of " + root.dataDate))
                    color: root.standingsError || root.stale ? Color.urgent : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.space(11)
                    wrapMode: Text.WordWrap
                }
            }

            Row {
                id: divisions
                visible: root.page === "standings"
                anchors.top: header.bottom
                anchors.topMargin: Style.space(18)
                anchors.bottom: footer.top
                anchors.bottomMargin: Style.space(16)
                width: parent.width
                spacing: Style.space(24)
                Repeater {
                    id: divisionRepeater
                    model: root.divisionNames
                    delegate: DivisionTable {
                        required property string modelData
                        required property int index
                        readonly property int rowOffset: index === 0 ? 0 : root.divisionTeams(root.divisionNames[0]).length
                        width: (divisions.width - divisions.spacing) / 2
                        height: divisions.height
                        division: modelData
                        teams: root.divisionTeams(modelData)
                        selectedCode: root.selectedTeam ? root.selectedTeam.code : ""
                        cursorIndex: root.cursorIndex - rowOffset
                        onTeamSelected: function(team, rowIndex) {
                            root.cursorIndex = rowOffset + rowIndex
                            root.selectTeam(team)
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: divisions
                visible: root.page === "standings" && root.conferenceTeams.length === 0
                text: standingsProcess.running ? "Loading standings…" : "Standings unavailable\nClick refresh to try again."
                color: Color.muted
                horizontalAlignment: Text.AlignHCenter
                font.family: Style.font.family
                font.pixelSize: Style.space(13)
            }

            SettingsView {
                id: notificationSettings
                visible: root.page === "settings"
                anchors.top: header.bottom
                anchors.topMargin: Style.space(16)
                anchors.bottom: parent.bottom
                width: parent.width
                teams: root.teams
                onCloseRequested: root.close()
            }

            EmailLogView {
                id: emailLog
                visible: root.page === "log"
                anchors.top: header.bottom
                anchors.topMargin: Style.space(16)
                anchors.bottom: parent.bottom
                width: parent.width
                onCloseRequested: root.close()
            }

            Column {
                id: footer
                visible: root.page === "standings"
                anchors.bottom: parent.bottom
                width: parent.width
                spacing: Style.space(7)
                Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.12) }
                Text {
                    width: parent.width
                    text: root.selectedTeam ? root.selectedTeam.name + " · Next game" : "Click a team to see its next game"
                    color: root.selectedTeam ? Color.foreground : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.space(12)
                    font.bold: root.selectedTeam !== null
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: root.selectedTeam !== null
                    text: root.gameError || (root.game ? root.game.away + " at " + root.game.home : (scheduleProcess.running || root.pendingTeam !== "" ? "Loading schedule…" : "No upcoming game scheduled."))
                    color: root.gameError ? Color.urgent : Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.space(13)
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: root.selectedTeam !== null && root.game !== null
                    text: root.formatGameTime()
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.space(13)
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    visible: root.selectedTeam !== null && root.game !== null
                    text: root.game ? [root.game.kind, root.game.venue, root.gameStale ? "Cached schedule" : "Local time"].filter(function(s) { return s !== "" }).join(" · ") : ""
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.space(10)
                    wrapMode: Text.WordWrap
                }
                Text {
                    text: "GP games played · OT overtime losses · PTS points"
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.space(10)
                }
            }
        }
    }
}
