import os
import json
import time
import shutil
import argparse


from oliwo_weights.xoliwo  import OliwoModel
from oliwo_weights.xcodiff import (
    find_differences, 
    find_jpg_images, 
    create_directory_force,
    copy_directory_contents,
    grab_file_from_path,
    get_matching_prod_names
)

def get_absolute_root_directory():
    """Get the correct path to retruxosaproject directory based on actual structure"""
    # Get the directory where this script is located (product_scan/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Go up one level to project root (retrux-shelf-eye/), then into retruxosaproject
    project_root = os.path.dirname(script_dir)
    retrux_path = os.path.join(project_root, 'retruxosaproject', 'app_root', 'active_state')
    
    print(f"Script directory: {script_dir}")
    print(f"Project root: {project_root}")
    print(f"Retrux path: {retrux_path}")
    
    # Check if path exists
    if not os.path.exists(retrux_path):
        # Alternative: if running from different location
        alt_retrux_path = os.path.join(script_dir, '..', 'retruxosaproject', 'app_root', 'active_state')
        alt_retrux_path = os.path.abspath(alt_retrux_path)
        print(f"Alternative path: {alt_retrux_path}")
        
        if os.path.exists(alt_retrux_path):
            return alt_retrux_path
        else:
            print(f"ERROR: Neither path exists:")
            print(f"  Primary: {retrux_path}")
            print(f"  Alternative: {alt_retrux_path}")
            print(f"Current working directory: {os.getcwd()}")
            
            # Create the directory structure if it doesn't exist
            try:
                os.makedirs(retrux_path, exist_ok=True)
                print(f"Created directory structure: {retrux_path}")
                return retrux_path
            except Exception as e:
                raise FileNotFoundError(f"Cannot find or create retruxosaproject directory: {e}")
    
    return retrux_path

# Use the function to get correct path
absolute_root_directory = get_absolute_root_directory()

def predict_single_file(oliwo : OliwoModel, src : str, trg : str) -> None:
    oliwo.predict_to_file(
        image_path  = src,
        output_file = trg
    )

def load_products(latest_frame_file : str):
    global absolute_root_directory

    # get directories - fix path structure
    parent_dir = os.path.dirname(absolute_root_directory)  # app_root
    src_dir = os.path.join(absolute_root_directory, 'devices')
    ltt_dir = os.path.join(parent_dir, 'last_state')  # Fixed: use parent_dir
    inf_dir = os.path.join(parent_dir, 'product_information')  # Fixed: use parent_dir
    stt_dir = os.path.join(parent_dir, 'product_state')  # Fixed: use parent_dir

    fname, base_name = grab_file_from_path(latest_frame_file)
    prod_info_jsf = os.path.join(inf_dir, f"{base_name}.json")
    
    # Check if product info file exists
    if not os.path.exists(prod_info_jsf):
        print(f"ERROR: Product info file not found: {prod_info_jsf}")
        raise FileNotFoundError(f"Product info file not found: {prod_info_jsf}")
    
    with open(prod_info_jsf, 'r') as file:
        products_list : list[dict[str, any]] = json.load(file)

    # Load existing product state or create initial state
    prod_state_jsf = os.path.join(stt_dir, f"{base_name}.json")
    if os.path.exists(prod_state_jsf):
        with open(prod_state_jsf, 'r') as file:
            product_latest_state : list[dict[str, any]] = json.load(file)
    else:
        # Create initial state - assuming everything is full initially
        product_latest_state = [
            {
                'name'   : x['name'],
                'coords' : x['coords'],
                'state'  : 'full'
            }
            for x in products_list
        ]

    return (products_list, product_latest_state)


def compute_device_diff(oliwo : OliwoModel, image_file : str) -> tuple:
    global absolute_root_directory

    # get directories - fix path structure
    parent_dir = os.path.dirname(absolute_root_directory)  # app_root
    src_dir = os.path.join(absolute_root_directory, 'devices')
    ltt_dir = os.path.join(parent_dir, 'last_state')  # Fixed: use parent_dir
    inf_dir = os.path.join(parent_dir, 'product_information')  # Fixed: use parent_dir
    stt_dir = os.path.join(parent_dir, 'product_state')  # Fixed: use parent_dir
    
    # get file names
    latest_frame_file   = os.path.join(src_dir, f"{image_file}.jpg")
    previous_frame_file = os.path.join(ltt_dir, f"{image_file}.jpg")

    # Check if files exist before processing
    if not os.path.exists(latest_frame_file):
        print(f"ERROR: Latest frame not found: {latest_frame_file}")
        return [], []
        
    if not os.path.exists(previous_frame_file):
        print(f"INFO: Previous frame not found: {previous_frame_file}")
        print("This is normal during first scan - no differences to detect")
        diffrence_xyxy = []
    else:
        # find all differences between them
        print(f"Comparing: {previous_frame_file} -> {latest_frame_file}")
        diffrence_xyxy = find_differences(previous_frame_file, latest_frame_file)
        print(f"Found {len(diffrence_xyxy)} differences")

    # predict all boxes in current frame
    latest_image = oliwo.load_image(latest_frame_file)
    predicted_xyxy = oliwo.predict(latest_image)
    print(f"Predicted {len(predicted_xyxy)} objects in current frame")
    
    # Load product info - check if file exists first
    fname, base_name = grab_file_from_path(latest_frame_file)
    prod_info_jsf = os.path.join(inf_dir, f"{base_name}.json")
    
    if not os.path.exists(prod_info_jsf):
        print(f"ERROR: Product info file not found: {prod_info_jsf}")
        print("Run setup first to create product information")
        return diffrence_xyxy, predicted_xyxy
    
    products_list, product_latest_state = load_products(latest_frame_file)

    # get valid product names that match with detected boxes
    img_diff_names = get_matching_prod_names(diffrence_xyxy, products_list)
    img_pred_names = get_matching_prod_names(predicted_xyxy, products_list)

    print(f"Products with differences: {img_diff_names}")
    print(f"Products with objects detected: {img_pred_names}")

    # Update product states based on detection results
    for i in range(len(product_latest_state)):
        prod = product_latest_state[i]
        prod_name = prod['name']

        # check if product exists in both difference and prediction
        exist_in_diff = any([xn == prod_name for xn in img_diff_names])
        exist_in_pred = any([xn == prod_name for xn in img_pred_names])

        # State logic:
        # - If there's a difference AND objects detected -> reduced
        # - If there's a difference AND no objects detected -> empty  
        # - If no difference detected -> keep previous state
        if exist_in_diff and exist_in_pred:
            product_latest_state[i]['state'] = 'reduced'
            print(f"  {prod_name}: reduced")
        elif exist_in_diff and not exist_in_pred:
            product_latest_state[i]['state'] = 'empty'
            print(f"  {prod_name}: empty")
        # If no difference, keep previous state (no change)

    # Save updated product state
    os.makedirs(stt_dir, exist_ok=True)
    prod_state_jsf = os.path.join(stt_dir, f"{base_name}.json")
    with open(prod_state_jsf, "w") as f:
        json.dump(product_latest_state, f, indent = 2)
    
    print(f"Updated product state saved to: {prod_state_jsf}")

    return diffrence_xyxy, predicted_xyxy

def update_last_state(current_frame_path: str):
    """Update last_state with current frame after inference"""
    global absolute_root_directory
    
    parent_dir = os.path.dirname(absolute_root_directory)
    last_state_dir = os.path.join(parent_dir, 'last_state')
    os.makedirs(last_state_dir, exist_ok=True)
    
    fname, base_name = grab_file_from_path(current_frame_path)
    last_state_path = os.path.join(last_state_dir, f"{base_name}.jpg")
    
    # Copy current frame to last_state (will be used for next comparison)
    shutil.copy2(current_frame_path, last_state_path)
    print(f"Updated last_state: {last_state_path}")

def setup_directories(oliwo : OliwoModel) -> None:
    global absolute_root_directory

    print(f"Setting up directories with root: {absolute_root_directory}")

    # original image dir
    source_dir  = os.path.join(absolute_root_directory, 'devices')
    
    # Check if source directory exists
    if not os.path.exists(source_dir):
        print(f"ERROR: Source directory does not exist: {source_dir}")
        print("Please make sure images are placed in the devices directory")
        return
    
    image_files = find_jpg_images(source_dir)
    print(f"Found {len(image_files)} Device Images")
    
    if len(image_files) == 0:
        print("ERROR: No JPG images found in devices directory")
        print(f"Please add some .jpg images to: {source_dir}")
        return

    # setup state directories with proper parent path
    parent_dir = os.path.dirname(absolute_root_directory)  # app_root
    
    print("Setting up last_state directory")
    last_state_dir = os.path.join(parent_dir, 'last_state')
    create_directory_force(last_state_dir)
    # Copy current images to last_state for initial setup
    copy_directory_contents(
        source_dir = source_dir,
        target_dir = last_state_dir
    )

    print("Setup Product Information Directory")
    information_dir = os.path.join(parent_dir, 'product_information')
    create_directory_force(information_dir)
    
    print("Setup Product State Directory")
    product_state_dir = os.path.join(parent_dir, 'product_state')
    create_directory_force(product_state_dir)
    
    # STEP 1: Create product information files first
    print("Step 1: Creating product information files...")
    for image_file_path in image_files:
        print(f"Processing image: {os.path.basename(image_file_path)}")

        # grab base path
        fname, base_name = grab_file_from_path(image_file_path)

        # output file
        out_file = os.path.join(information_dir, f"{base_name}.json")
        oliwo.predict_to_file(
            image_path  = image_file_path,
            output_file = out_file
        )

    print("Step 1 completed: All product information files created")

    # STEP 2: Create initial product state files
    print("Step 2: Creating initial product state files...")
    for image_path in image_files:
        _, base_name = grab_file_from_path(image_path)
        try:
            # This will create initial state files
            diffrence_xyxy, predicted_xyxy = compute_device_diff(oliwo, base_name)
            print(f"  Initialized state for: {base_name}")
        except Exception as e:
            print(f"  ERROR initializing state for {base_name}: {e}")

    print("Setup Complete Successfully!")
    print(f"Created:")
    print(f"  - {len(image_files)} files in last_state/")
    print(f"  - {len(image_files)} files in product_information/") 
    print(f"  - {len(image_files)} files in product_state/")

def running_service(oliwo : OliwoModel):
    global absolute_root_directory

    # get directories - fix path structure
    parent_dir = os.path.dirname(absolute_root_directory)  # app_root
    src_dir = os.path.join(absolute_root_directory, 'devices')
    ltt_dir = os.path.join(parent_dir, 'last_state')  # Fixed: use parent_dir
    inf_dir = os.path.join(parent_dir, 'product_information')  # Fixed: use parent_dir
    stt_dir = os.path.join(parent_dir, 'product_state')  # Fixed: use parent_dir
    vos_dir = os.path.join(absolute_root_directory, 'product_visual')
    os.makedirs(vos_dir, exist_ok = True)

    image_file_list = find_jpg_images(src_dir)
    print(f"Found {len(image_file_list)} Devices for monitoring")

    if len(image_file_list) == 0:
        print("ERROR: No image files found to monitor")
        print("Make sure images are present in devices directory")
        return

    # image files modification time tracking
    last_modified_time = {}
    for file_path in image_file_list:
        last_modified_time[file_path] = 0

    print("Starting monitoring service...")
    scan_count = 0

    try:
        while True:
            
            # enumerate the file list
            for file_path in image_file_list:
            
                # Check if the file has been modified
                try:
                    current_modified = os.path.getmtime(file_path)
                except OSError:
                    # File might not exist or be accessible
                    continue
                
                # check current modified time
                if current_modified == last_modified_time[file_path]:
                    continue
                
                # File has been modified - process it
                file_name, base_name = grab_file_from_path(file_path)
                scan_count += 1
                print(f"\n=== SCAN #{scan_count} ===")
                print(f"Processing updated file: {file_name}")
                print(f"Modified time: {time.ctime(current_modified)}")
                
                try:
                    # Perform inference and state comparison
                    diffrence_xyxy, predicted_xyxy = compute_device_diff(oliwo, base_name)

                    # Update last_state AFTER inference is complete
                    update_last_state(file_path)

                    # Update modification time only after successful processing
                    last_modified_time[file_path] = current_modified

                    # Load image for visual output
                    image = oliwo.load_image(file_path)

                    # Create visual overlay with detected objects
                    if predicted_xyxy:
                        overlayed = oliwo.overlay(
                            image, 
                            predicted_xyxy,
                            fill_alpha = 0,
                            line_width = 5
                        )

                        # Save visual output
                        output_path = os.path.join(vos_dir, file_name)
                        overlayed.save(output_path)
                        
                        print(f"Generated visual output: {output_path}")
                    
                    print(f"Scan #{scan_count} completed successfully")
                    print(f"  - Differences detected: {len(diffrence_xyxy)}")
                    print(f"  - Objects predicted: {len(predicted_xyxy)}")
                    
                except Exception as e:
                    print(f"Error processing {file_name}: {e}")

            time.sleep(2)  # Check for file updates every 2 seconds
            
    except KeyboardInterrupt:
        print("\nReceived Ctrl+C. Exiting gracefully...")
        print(f"Total scans performed: {scan_count}")
    

if __name__ == "__main__":
    print("Shelf Scanner - Fixed Path Version")

    # Print path information for debugging
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script location: {__file__}")
    print(f"Resolved root directory: {absolute_root_directory}")

    parser = argparse.ArgumentParser(description="Shelf Scan Service")
    subparsers = parser.add_subparsers(dest = "command",  required = True)

    # Predict command
    predict_parser = subparsers.add_parser("predict", help = "Predict Single File")
    predict_parser.add_argument("--input",  required = True, help = "Input image file")
    predict_parser.add_argument("--output", required = True, help = "Output JSON file")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help = "Setup environment")

    # Service command
    service_parser = subparsers.add_parser("service", help = "Start service")

    # Parse the Arguments 
    args = parser.parse_args()

    # selected ars
    selected_command = str(args.command)

    # setup model 
    print("Loading OliwoModel...")
    try:
        oliow_model_x = OliwoModel()
        print("OliwoModel loaded successfully")
    except Exception as e:
        print(f"ERROR: Failed to load OliwoModel: {e}")
        print("Make sure the oliwo_weights directory contains the required model files")
        exit(1)

    if selected_command == "predict":

        # prediction
        print("## Single Prediction Mode ##")
        predict_single_file(
            oliow_model_x, args.input, args.output
        )

    elif selected_command == "setup":
        print("# Setup Directory")
        setup_directories(oliow_model_x)

    elif selected_command == "service":
        print("Running Shelf Diff Service")
        running_service(oliow_model_x)

    else:
        print("Arguments need to be Selected")

    print("Exiting...")