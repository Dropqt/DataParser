        # Example for filling an email field
        #email_field = driver.find_element(By.ID, "email")
        #email_field.clear()
        #email_field.send_keys("petar@example.com")
        #print("Filled email field")
        
        # ======== STEP 2: HANDLE DROPDOWN MENUS ========
        # Example for selecting an option from a dropdown
        # Replace "city" with the actual ID of the dropdown
        #city_dropdown = Select(driver.find_element(By.ID, "city"))
        
        # Three ways to select an option:
        # 1. By visible text (what you see in the dropdown)
        #city_dropdown.select_by_visible_text("Beograd")
        
        # 2. By value (the value attribute in the HTML)
        # city_dropdown.select_by_value("BG")
        
        # 3. By index (position in the dropdown, starting from 0)
        # city_dropdown.select_by_index(1)


        
        # ======== STEP 3: HANDLE CHECKBOXES ========
        # Example for checking a checkbox
        # Replace "termsAgreed" with the actual ID of the checkbox
        #terms_checkbox = driver.find_element(By.ID, "termsAgreed")
        
        # Check if it's already checked
        #if not terms_checkbox.is_selected():
            #terms_checkbox.click()  # Click only if not already checked
           # print("Checked terms checkbox")
        
        # ======== STEP 4: HANDLE RADIO BUTTONS ========
        # Example for selecting a radio button
        # Replace "paymentMethod1" with the actual ID of the radio button
       # payment_radio = driver.find_element(By.ID, "paymentMethod1")
       # payment_radio.click()
        #print("Selected payment method radio button")
        
        # ======== STEP 5: SUBMIT THE FORM ========
        # Ask user if they want to submit
        #submit_form = input("Do you want to submit the form? (y/n): ")z


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.firefox import GeckoDriverManager
import time
import time
import re
from datetime import datetime, timedelta


import os
import glob
from pathlib import Path






def parse_login(file_path):
    counter = 0
    login=[]
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            login.append(line)
    return login




def rename_latest_download(new_name):
    """
    Rename the most recently downloaded file in the Downloads folder
    
    Args:
        new_name (str): The new base name for the file (without extension)
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Get the downloads directory path
    downloads_path = str(Path.home() / "Downloads")
    
    # Get all files in the downloads directory
    try:
        files = glob.glob(os.path.join(downloads_path, "*"))
    except Exception as e:
        print(f"Error accessing downloads folder: {e}")
        return False
    
    # Filter to only include files (not directories)
    files = [f for f in files if os.path.isfile(f)]
    
    if not files:
        print("No files found in downloads folder")
        return False
        
    # Sort files by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)
    
    # Get the most recent file
    latest_file = files[0]
    original_filename = os.path.basename(latest_file)
    print(f"Most recent file: {original_filename}")
    
    # Get the file extension
    _, file_ext = os.path.splitext(latest_file)
    if file_ext == '.pdf':
    # Create the new filename with original extension
        new_filename = f"{new_name}{file_ext}"
        new_filepath = os.path.join(downloads_path, new_filename)
        try:
            os.rename(latest_file, new_filepath)
            print(f"File renamed to: {new_filename}")
            #return True
        except Exception as e:
            print(f"Error renaming file: {e}")
            #return False

    else:
        print('Fajl nije pdf, ne mogu rename')
    
    # Rename the file


# Example usage






#Dataparser
# Function to parse the data file
def parse_data_file(file_path):
    people_data = []
    counter = 0
    
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            
            try:
                # First try with the most flexible pattern that can handle various formats
                # This pattern handles:
                # - Mixed case names
                # - Variable spacing
                # - With or without dashes before dates
                # - Different date formats (DD.MM, DD.MM.YY, DD-MM, etc.)
                # - Optional date ranges (05.10-10.10)
                
                # Initial split to handle the index
                parts = re.split(r'^(\d+)\.', line.strip())
                if len(parts) >= 3:
                    index = parts[1]
                    rest = parts[2].strip()
                    
                    # Extract the ID number (assuming it's a sequence of digits, at least 9 digits)
                    id_match = re.search(r'(\d{9,})', rest)
                    if id_match:
                        id_number = id_match.group(1)
                        
                        # Split the text before and after the ID
                        before_id = rest[:id_match.start()].strip()
                        after_id = rest[id_match.end():].strip()
                        
                        # Get the date pattern from after_id
                        date_match = re.search(r'(\d{2}[.-]\d{2}(?:[.-]\d{2,4})?(?:\s*[-–]\s*\d{2}[.-]\d{2}(?:[.-]\d{2,4})?)?)', after_id)
                        date_str = date_match.group(1) if date_match else after_id.strip()
                        
                        # Extract name parts
                        name_parts = before_id.strip().split()
                        if name_parts:
                            surname = name_parts[0]
                            name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ""
                            
                            # Create a dictionary for this person
                            person = {
                                'index': index,
                                'surname': surname,
                                'name': name,
                                'id_number': id_number,
                                'date': date_str,
                                'id': counter
                            }
                            counter += 1
                            people_data.append(person)
                            continue
            
            except Exception as e:
                print(f"Error processing line with flexible pattern: {e}")
            
            # If we get here, try the fallback pattern
            try:
                # Fallback regex patterns - try several formats
                patterns = [
                    # Standard format: number.SURNAME NAME ID_NUMBER DATE
                    r'^(\d+)\.([A-Za-zČĆŽŠĐčćžšđ]+)\s+([A-Za-zČĆŽŠĐčćžšđ\s]+)\s+(\d+)\s+(\d{2}[.-]\d{2}(?:[.-]\d{2,4})?(?:\s*[-–]\s*\d{2}[.-]\d{2}(?:[.-]\d{2,4})?)?)$',
                                
                    # Format with dash before date: number.SURNAME NAME ID_NUMBER -DATE
                    r'^(\d+)\.([A-Za-zČĆŽŠĐčćžšđ]+)\s+([A-Za-zČĆŽŠĐčćžšđ\s]+)\s+(\d+)\s*[-–]\s*(\d{2}[.-]\d{2}(?:[.-]\d{2,4})?(?:\s*[-–]\s*\d{2}[.-]\d{2}(?:[.-]\d{2,4})?)?)$',
                                
                    # More relaxed spacing: number.SURNAME NAME ID DATE
                    r'^(\d+)\.([A-Za-zČĆŽŠĐčćžšđ]+)\s+([A-Za-zČĆŽŠĐčćžšđ\s]+)\s+(\d+)(?:\s+|\s*[-–]\s*)(.+)$'
                ]
                
                match = None
                for pattern in patterns:
                    match = re.match(pattern, line)
                    if match:
                        break
                
                if match:
                    index = match.group(1)
                    surname = match.group(2)
                    name = match.group(3).strip()
                    id_number = match.group(4)
                    date_str = match.group(5)
                    
                    # Create a dictionary for this person
                    person = {
                        'index': index,
                        'surname': surname,
                        'name': name,
                        'id_number': id_number,
                        'date': date_str,
                        'id': counter
                    }
                    counter += 1
                    people_data.append(person)
                else:
                    print(f"Warning: Could not parse line: {line}")
                    
            except Exception as e:
                print(f"Error processing line with fallback patterns: {e}")
                print(f"Warning: Could not parse line: {line}")
    
    # Print the parsed data
    for person in people_data:
        print(f"Person #{person['index']}: {person['surname']} {person['name']}, ID: {person['id_number']}, Date: {person['date']}")
    
    return people_data

# Call the function



# Set up Firefox driver
def setup_driver():
    options = Options()
    service = Service(GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=options)
    print("Firefox browser opened")
    return driver

# Main function
def fill_eturista_form():
    user=mileta
    # URL to navigate to
    url = "https://www.portal.eturista.gov.rs/vauceri/rezervacija-smestaja"
    
    # Setup driver
    driver = setup_driver()
    print(f"Navigating to {url}")
    driver.get(url)

    print("Waiting for page to load...")
    time.sleep(5)
    first_name_field = driver.find_element(By.ID, "username")
    first_name_field.clear()  # Clear any existing text
    first_name_field.send_keys(user[0]) #changed so i can get multiple users if needed.
    print("Filled first name field")

    last_name_field = driver.find_element(By.ID, "passwordInput")
    last_name_field.clear()
    last_name_field.send_keys(user[1]) #changed so i can get multiple users if needed.
    print("Filled last name field")
    # Replace "submitButton" with the actual ID of the submit button
    #submit_button = driver.find_element(By.ID, "submitButton")
    submit_button=driver.find_element(By.XPATH, '//button[@type="submit"]')
    submit_button.click()
    print("Form submitted")
    time.sleep(3)
    # Keep browser open until user decides to close
    print("Preparing to go next round.")
    for i in range(len(parse_data)):
        try:


            name_field = driver.find_element(By.XPATH, '//*[@formcontrolname="ime"]')
            name_field.clear()  # Clear any existing text
            name_field.send_keys(parse_data[i]['name'])  # Input text
            print("Filled first name field after login")
            time.sleep(2)
            prezime_field =driver.find_element(By.XPATH, '//*[@formcontrolname="prezime"]')
            prezime_field.clear()
            prezime_field.send_keys(parse_data[i]['surname'])
            print("Filled last name field")
            time.sleep(1)
            jmbg_field =driver.find_element(By.XPATH, '//*[@formcontrolname="jmbg"]')
            jmbg_field.clear()
            jmbg_field.send_keys(parse_data[i]['id_number'])
            print("Filled JMBG field")
            time.sleep(1)
            try:
                jmbg_error= driver.find_element(By.CLASS_NAME, "mat-error")
                print('Greska u jmbgu, refresh?')
                driver.refresh()
            except NoSuchElementException:
                print('Nema greske u JMBG-u, idemo dalje')

            time.sleep(1)
            next_icon = driver.find_element(By.CSS_SELECTOR, "button[aria-describedby='cdk-describedby-message-4']")
            next_icon.click()
            print('clicked a button')

            #TODO Nadji nacin da ubacis datum
            #Dugmici za next i kako novosacuvani fajl da sacuvas pod istim imenom


            #Rename downloada
            #rename_latest_download('2025'+ ' '+(parse_data[i]['name']).upper()+" "+(parse_data[i]['surname']).upper())

        



        #Button click
            # Using CSS selector to find the icon containing "navigate_next"
            #next_button = driver.find_element(By.CSS_SELECTOR, "mat-icon.material-icons:contains('navigate_next')")
            # Or more precisely:
            #next_button = driver.find_element(By.CSS_SELECTOR, "mat-icon.mat-icon.material-icons")
            #next_button.click()


        except Exception as e:
            print(f"An error occurred: {e}")
            break
        finally:
            # Close the browser
            #driver.quit()
            #print("Browser closed")
            driver.refresh()
            print('trigger close?')




parse_data = parse_data_file('1-25.txt')
parse_login_data=parse_login('logins.txt')
majka=[parse_login_data[0],parse_login_data[1]]
mileta=[parse_login_data[2],parse_login_data[3]]

# Run the script
if __name__ == "__main__":
    fill_eturista_form()
