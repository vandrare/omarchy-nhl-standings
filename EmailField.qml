import QtQuick
import qs.Commons
import qs.Ui as Ui

Column {
    id: root
    signal edited(string value)
    property string label: ""
    property string hint: ""
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property alias password: input.password
    spacing: Style.space(6)
    Text {
        text: root.label
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.space(12)
    }
    Ui.TextField {
        id: input
        onTextEdited: root.edited(text)
        width: parent.width
        selectByMouse: true
        font.pixelSize: Style.space(12)
        maximumLength: root.password ? 32 : 254
    }
    Text {
        width: parent.width
        visible: root.hint !== ""
        text: root.hint
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.space(10)
        wrapMode: Text.WordWrap
    }
}
