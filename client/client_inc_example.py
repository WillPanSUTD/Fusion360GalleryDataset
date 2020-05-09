from pathlib import Path
import sys
import os
import json
from fusion_360_client import Fusion360Client

# Before running ensure the Fusion360Server is running
# and configured with the same host name and port number
HOST_NAME = "127.0.0.1"
PORT_NUMBER = 8080


def main():
    current_dir = Path(__file__).parent
    root_dir = current_dir.parent
    data_dir = root_dir / "data"
    output_dir = data_dir / "output"
    if not output_dir.exists():
        output_dir.mkdir()

    # SETUP
    # Create the client class to interact with the server
    client = Fusion360Client(f"http://{HOST_NAME}:{PORT_NUMBER}")
    # Clear to force close all documents in Fusion
    # Do this before a new reconstruction
    r = client.clear()
    # Example of how we read the response data
    response_data = r.json()
    print(f"[{r.status_code}] Response: {response_data['message']}")

    # INCREMENTAL RECONSTRUCT
    # Send a list of commands directly to the server to run in sequence
    # We need to load the json as a dict to reconstruct
    hex_design_json_file = data_dir / "Z0HexagonCutJoin_RootComponent.json"
    with open(hex_design_json_file) as file_handle:
        hex_design_json_data = json.load(file_handle)

    timeline = hex_design_json_data["timeline"]
    entities = hex_design_json_data["entities"]
    sketches = {}
    for timeline_object in timeline:
        entity_key = timeline_object["entity"]
        entity = entities[entity_key]
        if entity["type"] == "Sketch":
            sketches[entity_key] = add_sketch(client, entity, entity_key)
        elif entity["type"] == "ExtrudeFeature":
            add_extrude_feature(client, entity, entity_key, sketches)


def add_sketch(client, sketch, sketch_id):
    """Add a sketch to the design"""
    # First we need a plane to sketch on
    ref_plane = sketch["reference_plane"]
    ref_plane_type = ref_plane["type"]
    # Default to making a sketch on the XY plane
    sketch_plane = "XY"
    if ref_plane_type == "ConstructionPlane":
        # Use the name as a reference to the plane axis
        sketch_plane = ref_plane["name"]
    elif ref_plane_type == "BRepFace":
        # Identify the face by a point that sits on it
        sketch_plane = ref_plane["point_on_face"]
    r = client.add_sketch(sketch_plane)
    # Get the sketch name back
    response_json = r.json()
    sketch_name = response_json["data"]["sketch_name"]
    profile_ids = add_profiles(client, sketch_name, sketch["profiles"])
    return {
        "sketch_name": sketch_name,
        "profile_ids": profile_ids
    }


def add_profiles(client, sketch_name, profiles):
    """Add the sketch profiles to the design"""
    profile_ids = {}
    response_json = None
    for original_profile_id, profile in profiles.items():
        for loop in profile["loops"]:
            # Only draw the outside loop, not the inside loop
            # i.e. the holes
            if loop["is_outer"] is True:
                curves = loop["profile_curves"]
                for curve in curves:
                    if curve["type"] != "Line3D":
                        print(f"Warning: Unsupported curve type - {curve['type']}")
                        continue

                    r = client.add_line(sketch_name, curve["start_point"], curve["end_point"])
                    response_json = r.json()

        # Look at the final response and pull out profiles
        response_data = response_json["data"]
        # Pull out the first profile
        profile_ids[original_profile_id] = next(iter(response_data["profiles"]))
    return profile_ids


def add_extrude_feature(client, extrude_feature, extrude_feature_id, sketches):
    # We only handle a single profile
    original_profile_id = extrude_feature["profiles"][0]["profile"]
    original_sketch_id = extrude_feature["profiles"][0]["sketch"]
    # Use the original ids to find the new ids
    sketch_name = sketches[original_sketch_id]["sketch_name"]
    profile_id = sketches[original_sketch_id]["profile_ids"][original_profile_id]
    # Pull out the other extrude parameters
    distance = extrude_feature["extent_one"]["distance"]["value"]
    operation = extrude_feature["operation"]
    # Add the extrude
    r = client.add_extrude(sketch_name, profile_id, distance, operation)
    response_json = r.json()
    response_data = response_json["data"]

if __name__ == "__main__":
    main()
