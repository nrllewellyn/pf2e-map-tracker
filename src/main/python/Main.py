from GraphExport import create_room_graph

if __name__ == "__main__":
    # json_path = "../resources/roomData.json"
    json_path = "../resources/testData.json"
    create_room_graph(json_path, "../../../target/interactive_room_graph.html")
