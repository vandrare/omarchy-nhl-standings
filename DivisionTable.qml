import QtQuick
import qs.Commons

Item {
    id: root
    property string division: ""
    property var teams: []
    property string selectedCode: ""
    property int cursorIndex: -1
    signal teamSelected(var team, int rowIndex)

    function ensureVisible(index) {
        list.positionViewAtIndex(index, ListView.Contain)
    }

    onDivisionChanged: list.contentY = 0

    Column {
        id: header
        width: parent.width
        spacing: Style.space(12)
        Text {
            text: root.division + " Division"
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.space(15)
            font.bold: true
        }
        Row {
            width: parent.width
            Text {
                width: parent.width - Style.space(200)
                text: "TEAM"
                leftPadding: Style.space(10)
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.space(10)
            }
            Repeater {
                model: ["GP", "W", "L", "OT", "PTS"]
                delegate: Text {
                    required property string modelData
                    width: Style.space(40)
                    text: modelData
                    color: Color.muted
                    horizontalAlignment: Text.AlignHCenter
                    font.family: Style.font.family
                    font.pixelSize: Style.space(10)
                    font.bold: modelData === "PTS"
                }
            }
        }
        Rectangle { width: parent.width; height: 1; color: Util.alpha(Color.foreground, 0.12) }
    }

    ListView {
        id: list
        anchors.top: header.bottom
        anchors.topMargin: Style.space(5)
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.teams
        delegate: Rectangle {
            id: teamRow
            required property var modelData
            required property int index
            width: list.width
            height: Style.space(29)
            radius: Style.space(4)
            readonly property bool selected: root.selectedCode === modelData.code
            color: selected ? Util.alpha(Color.accent, 0.14) : (rowMouse.containsMouse || root.cursorIndex === index ? Util.alpha(Color.foreground, 0.07) : "transparent")
            Row {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                Item {
                    width: parent.width - Style.space(200)
                    height: teamRow.height
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Style.space(8)
                        Text {
                            width: Style.space(24)
                            text: teamRow.modelData.divisionRank || teamRow.index + 1
                            color: Color.muted
                            horizontalAlignment: Text.AlignRight
                            font.family: Style.font.family
                            font.pixelSize: Style.space(11)
                        }
                        Image {
                            width: Style.space(22)
                            height: Style.space(20)
                            source: teamRow.modelData.logo
                            asynchronous: true
                            fillMode: Image.PreserveAspectFit
                            sourceSize: Qt.size(44, 40)
                        }
                        Text {
                            width: Math.max(0, teamRow.width - Style.space(272))
                            text: teamRow.modelData.name
                            elide: Text.ElideRight
                            color: teamRow.selected ? Color.accent : Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.space(12)
                        }
                    }
                }
                Repeater {
                    model: [teamRow.modelData.gp, teamRow.modelData.w, teamRow.modelData.l, teamRow.modelData.ot, teamRow.modelData.pts]
                    delegate: Text {
                        required property var modelData
                        required property int index
                        width: Style.space(40)
                        text: modelData
                        color: index === 4 ? Color.foreground : Color.muted
                        horizontalAlignment: Text.AlignHCenter
                        font.family: Style.font.family
                        font.pixelSize: Style.space(12)
                        font.bold: index === 4
                    }
                }
            }
            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.teamSelected(teamRow.modelData, teamRow.index)
            }
        }
    }
}
