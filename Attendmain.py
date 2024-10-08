###################################################################################
#Importing all required Modules
from facenet_pytorch import MTCNN, InceptionResnetV1
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import streamlit as st
from Test import test
from Utils import tts
import pandas as pd
import numpy as np
import random,string
import datetime
import sqlite3
import smtplib
import base64
import shutil
import torch
import cv2
import os
from streamlit_option_menu import option_menu
load_dotenv()
##############################################################################
##############################################################################
#reusable variable and terms
allowed_image_type = ['.png', 'jpg', '.jpeg']
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VISITOR_DB = os.path.join(ROOT_DIR, "Visitor_database")
VISITOR_HISTORY = os.path.join(ROOT_DIR, "Visitor_history")
COLOR_DARK  = (0, 0, 153)
COLOR_WHITE = (255, 255, 255)
COLS_INFO   = ['Name']
COLS_ENCODE = [f'v{i}' for i in range(512)]
DB_PATH     = os.path.join(ROOT_DIR, "Data/database.db")
####################################################################################
#################################################################################
## Common function for attendance system
def generate_workplace_id(school_name):
    sanitized_name = ''.join(char for char in school_name.upper() if char.isalnum())
    prefix = sanitized_name[:3]  
    if len(prefix) < 3:
        prefix = prefix.ljust(3, 'X')
    numeric_part = ''.join(random.choices(string.digits, k=5))
    return prefix + numeric_part


def BGR_to_RGB(image_in_array):
    return cv2.cvtColor(image_in_array, cv2.COLOR_BGR2RGB)
##############################################################################

##############################################################################
## Database
def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    encoding_columns = ', '.join(f'{col} REAL' for col in COLS_ENCODE)
    

    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS visitors (
        Unique_ID INTEGER,
        Name TEXT NOT NULL,
        Email TEXT NOT NULL UNIQUE,
        Workplace TEXT NOT NULL,
        Job_role TEXT NOT NULL,
        {encoding_columns}
    )
    ''')


    cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        ID TEXT,
        visitor_name TEXT,
        timing TIMESTAMP,
        status TEXT,
        image_path TEXT
    )
    ''')


    conn.commit()
    conn.close()

def add_data_db(df):
    conn = connect_db()
    cursor = conn.cursor()

    expected_columns = ['Unique_ID', 'Name', 'Workplace', 'Job_role', 'Email'] + COLS_ENCODE
    df = df[expected_columns]  

    columns = ', '.join(expected_columns)
    placeholders = ', '.join(['?'] * len(expected_columns))
    sql = f"INSERT INTO visitors ({columns}) VALUES ({placeholders})"


    data = df.to_records(index=False).tolist()


    cursor.executemany(sql, data)
    conn.commit()
    conn.close()

def get_data_from_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM visitors
    ''')
    data = cursor.fetchall()
    conn.close()
    
    df = pd.DataFrame(data, columns=['Unique_ID', 'Name','Email','Workplace','job_role'] + COLS_ENCODE)
    return df
################################################################################
######################################################################
## view attendance and recording of admin
def add_attendance(id, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.datetime.now()
    dtString = now.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    INSERT INTO attendance (ID, visitor_name, Timing, Image_Path)
    VALUES (?, ?, ?, ?)
    ''', (id, name, dtString, f'{id}.jpg'))
    
    conn.commit()
    conn.close()

def get_attendance_records():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM attendance
    ''')
    data = cursor.fetchall()
    conn.close()
    
    df = pd.DataFrame(data, columns=['ID', 'visitor_name', 'Timing','status','Image_Path'])
    return df
#################################################################################
#################################################################### ###########
### croping or preprocessing of image
def crop_image_with_ratio(img, height, width, middle):
    h, w = img.shape[:2]
    h = h - h % 4
    new_w = int(h / height) * width
    startx = middle - new_w // 2
    endx = middle + new_w // 2
    if startx <= 0:
        cropped_img = img[0:h, 0:new_w]
    elif endx >= w:
        cropped_img = img[0:h, w-new_w:w]
    else:
        cropped_img = img[0:h, startx:endx]
    return cropped_img
##########################################################################
################################################################################
##  clear admin records
def connect_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    return conn
def cleardatabase():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM visitors")
    
    conn.commit()
    conn.close()
    
    tts('Visitor database cleared successfully!')
    st.success('Visitor database cleared successfully!')

    if not os.path.exists(VISITOR_DB):
        os.mkdir(VISITOR_DB)
################################################################################
################################################################################
# clear recent history
def clearrecenthistory():
    conn = connect_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM attendance")
    
    conn.commit()
    conn.close()
    
    shutil.rmtree(VISITOR_HISTORY, ignore_errors=True)
    os.mkdir(VISITOR_HISTORY)
    
    tts('Recent history cleared successfully!')
    st.success('Recent history cleared successfully!')
###################################################################################
##################################################################################
### keeping all models and 
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
mtcnn = MTCNN(
        image_size=160, margin=0, min_face_size=20,
        thresholds=[0.6, 0.7, 0.7], factor=0.709, post_process=True,
        device=device, keep_all=True
        )
################################################################################
################################################################################
## View attendance
def view_attendance():
    st.markdown(f"<h2 style='text-align: center;color:white'>Attendance Records</h2>", unsafe_allow_html=True)

    df_combined = get_attendance_records()

    if df_combined.empty:
        st.warning("No attendance records found.")
        return

    df_combined.sort_values(by='Timing', ascending=False, inplace=True)
    df_combined.reset_index(drop=True, inplace=True)

    def encode_image(image_path):
        full_image_path = os.path.join(VISITOR_HISTORY, image_path)
        if image_path and os.path.isfile(full_image_path):
            try:
                with open(full_image_path, "rb") as image_file:
                    encoded = base64.b64encode(image_file.read()).decode()
                    return f"data:image/jpeg;base64,{encoded}"
            except Exception as e:
                st.error(f"Error encoding image {image_path}: {e}")
                return None
        return None

    # Apply image encoding to the 'Image_Path' column
    df_combined['image'] = df_combined['Image_Path'].apply(encode_image)

    # Check if the 'image' column contains encoded images
    if not df_combined['image'].isnull().all():
        try:
            st.data_editor(
                df_combined.drop(columns=["Image_Path"]),
                column_config={
                    "ID": st.column_config.Column("ID"),
                    "visitor_name": st.column_config.Column("Visitor Name"),
                    "Timing": st.column_config.Column("Timing"),
                    "image": st.column_config.ImageColumn(
                        "Visitor Image", help="Preview of visitor images"
                    )
                },
                hide_index=True,
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error displaying attendance data: {e}")
    else:
        st.warning("No images available for display.")
#################################################################################
#################################################################################
# Viewing all registered person
def view_registered_persons():
    df = get_data_from_db()
    
    if df.empty:
        st.warning("No registered persons found.")
        return
    st.markdown(f"<h4 style='text-align: center;color:white'>Registered Persons List</h4>", unsafe_allow_html=True)

    
    st.dataframe(df[['Unique_ID', 'Name', 'Email','Workplace', 'job_role']], use_container_width=True, hide_index=True)
############################################################################################
def add_attendance(visitor_id, name_visitor, current_time, image_path):
    conn = connect_db()
    cursor = conn.cursor()
    today_date = current_time.date()

    # Check if an entry exists for today (status = 'Entry')
    query = """
    SELECT timing, status
    FROM attendance
    WHERE ID = ? AND DATE(timing) = ? AND status = 'Entry'
    """
    cursor.execute(query, (visitor_id, today_date))
    record = cursor.fetchone()

    if record:
        # If an entry exists, mark this event as an "Exit"
        status = "Exit"
        try:
            insert_query = """
            INSERT INTO attendance (ID, visitor_name, timing, status, image_path)
            VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(insert_query, (visitor_id, name_visitor, current_time, status, image_path))
            conn.commit()  # Commit the new "Exit" row
            tts(f"Exit marked for {name_visitor}")
            st.info(f"Exit marked for {name_visitor}")
        except Exception as e:
            conn.rollback()  # Rollback in case of error
            st.error(f"Error marking exit: {e}")
    else:
        # If no entry exists for today, mark this event as an "Entry"
        status = "Entry"
        try:
            insert_query = """
            INSERT INTO attendance (ID, visitor_name, timing, status, image_path)
            VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(insert_query, (visitor_id, name_visitor, current_time, status, image_path))
            conn.commit()  # Commit the new "Entry" row
            tts(f"Entry marked for {name_visitor}")
            st.success(f"Entry marked for {name_visitor}")
        except Exception as e:
            conn.rollback()  # Rollback in case of error
            st.error(f"Error marking entry: {e}")
    
    cursor.close()
    conn.close()

######################################################################
#marking of attendance
def Takeattendance():
    st.markdown(f"<h2 style='text-align: center;color:white'>Mark your Attendance</h2>", unsafe_allow_html=True)
    visitor_id = st.text_input("Enter your Unique ID:", '', max_chars=8)
    if not visitor_id:
        st.error("Please enter your Unique ID.")
        return
    
    current_time = datetime.datetime.now()
    
    st.info("Ensure only your face is visible to the camera for attendance.")
    tts("Ensure only your face is visible to the camera for attendance.")
    
    img_file_buffer = st.camera_input("Take a picture")
    if img_file_buffer is not None:
        bytes_data = img_file_buffer.getvalue()
        image_array = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
        image_array_copy = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
        
        # Save the image to visitor history
        image_path = os.path.join(VISITOR_HISTORY, f'{visitor_id}.jpg')
        with open(os.path.join(VISITOR_HISTORY, f'{visitor_id}.jpg'), 'wb') as file:
            file.write(img_file_buffer.getbuffer())
            tts('Image Saved Successfully!')
            st.success('Image Saved Successfully!')
        
        # Detect faces in the image using MTCNN
        boxes, probs = mtcnn.detect(image_array, landmarks=False)
        
        if boxes is not None:
            boxes_int = [[int(box[0]), int(box[1]), int(box[2]), int(box[3])] for box in boxes]
            aligned = []
            rois = []
            spoofs = []
            can = []
            for idx, box in enumerate(boxes_int):
                img = crop_image_with_ratio(image_array, 160, 160, int((box[0] + box[2]) / 2))
                spoof = test(img, "./resources/anti_spoof_models", device)
                if spoof <= 1:
                    spoofs.append("REAL")
                    can.append(idx)
                    aligned_face = mtcnn(img)
                    if aligned_face is not None:
                        encodesCurFrame = resnet(aligned_face.to(device)).detach().cpu()
                        aligned.append(encodesCurFrame)
                else:
                    spoofs.append("FAKE")
            
            if len(aligned) > 0:
                similarity_threshold = 0.5
                flag_show = False
                
                for face_idx in can:
                    database_data = get_data_from_db()
                    face_encodings = database_data[COLS_ENCODE].values
                    dataframe = database_data[COLS_INFO]
                    face_to_compare = aligned[face_idx].numpy()
                    similarity = np.dot(face_encodings, face_to_compare.T)
                    matches = similarity > similarity_threshold
                    
                    if matches.any():
                        idx = np.argmax(similarity[matches])
                        dataframe_new = dataframe.iloc[idx]
                        name_visitor = dataframe_new['Name']
                        
                        # Record the current time and mark attendance (either Entry or Exit)
                        add_attendance(visitor_id, name_visitor, current_time, image_path)
                        flag_show = True
                        (left, top, right, bottom) = (boxes_int[face_idx])
                        rois.append(image_array_copy[top:bottom, left:right].copy())
                        
                        cv2.rectangle(image_array_copy, (left, top), (right, bottom), COLOR_DARK, 2)
                        cv2.rectangle(image_array_copy, (left, bottom + 35), (right, bottom), COLOR_DARK, cv2.FILLED)
                        font = cv2.FONT_HERSHEY_DUPLEX
                        cv2.putText(image_array_copy, f"#{name_visitor}", (left + 5, bottom + 25), font, .55, COLOR_WHITE, 1)
                    else:
                        tts('No Match Found for the given Similarity Threshold!')
                        st.error(f'No Match Found for the given Similarity Threshold! for face#{face_idx}')
                        st.info('Please Update the database for a new person or click again!')
                        add_attendance(visitor_id, 'Unknown', current_time, image_path)
                
                if flag_show:
                    st.image(BGR_to_RGB(image_array_copy), width=720)
            else:
                tts('No real faces detected')
                st.error('No real faces detected')
        else:
            tts('No human face detected.')
            st.error('No human face detected.')


def send_email(recipient_email, subject, body,unique_id):
    sender_email =  st.secrets["smtp"]["username"]
    sender_password = st.secrets["smtp"]["password"]

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);">
            <h2 style="color: #4CAF50; text-align: center;">Hello {recipient_email.split('@')[0]},</h2>
            <p style="font-size: 18px; line-height: 1.5;text-align: center; margin: 20px 0;color:blue">
                {body}
            </p>
            <p style="font-size: 18px; font-weight: bold; color: #FF5722; text-align: center; margin: 20px 0;">
                Your Unique ID: <span style="background-color: #FFFF00; padding: 5px 10px; border-radius: 5px; font-weight: bold; color: #333;">{unique_id}</span>
            </p>
            <p style="font-size: 14px; color: #555; text-align: center;">
                Best regards,<br>
                <strong>The Team</strong>
            </p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        server.quit()
        st.success(f"Unique ID sent to {recipient_email}")
    except Exception as e:
        st.error(f"Failed to send email: {str(e)}")
######################################################################
######################################################################
## Adding person

def personadder():
    face_name = st.text_input('Name:')
    email = st.text_input('Email:')
    
    roles = {
        "School": ["Vice Principal/Assistant Principal", "Grade 1 Students", "Grade 2 Students", "Grade 3 Students", "Grade 4 Students", "Grade 5 Students", "Grade 6 Students", "Grade 7 Students", "Grade 8 Students", "Grade 9 Students", "Grade 10 Students", "Grade 11 Students", "Grade 12 Students", "Classroom Teacher", "Special Education Teacher", "Teaching Assistant/Paraprofessional", "Subject Specialist (e.g., Math, Science)", "Extracurricular Activities Coordinator"],
        "University": ["Vice President/Chancellor", "Professor", "Associate Professor", "Assistant Professor", "Lecturer", "Teaching Assistant", "Research Scientist", "Postdoctoral Fellow", "Department Chair", "Registrar", "Academic Advisor", "Campus Security Officer", "IT Specialist", "Lab Technician", "Career Services Coordinator", "Library Director", "Facilities Manager"],
        "Hospital": ["Administrator", "Physician/Doctor", "Surgeon", "Anesthesiologist", "Registered Nurse", "Nurse Practitioner", "Medical Assistant", "Pharmacist", "Radiologic Technologist", "Lab Technician", "Physical Therapist", "Occupational Therapist", "Billing Specialist", "Patient Care Technician", "Phlebotomist", "Dietitian/Nutritionist", "Housekeeping Staff"],
        "Office": ["Office Manager", "Manager", "Assistant", "IT Specialist", "HR Specialist", "Receptionist", "Executive Assistant", "Operations Manager", "Project Manager", "Marketing Manager", "Accountant", "Financial Analyst", "Sales Representative", "Customer Service Representative", "Network Administrator"]
    }

    workplace = st.session_state.get('work_place', 'school')
    workplace_name = st.session_state.get('workplace_name', 'school')
    # st.subheader(workplace)
    # st.subheader(workplace_name)

    if workplace:
        job_roles = roles.get(workplace, [])
    else:
        job_roles = []

    job = st.selectbox("Select your job role",job_roles)
    img_file_buffer = None

    pic_option = st.selectbox('Upload Picture',
                              options=["Upload your Profile Picture", "Take a Picture with Cam"], index=None)

    if pic_option == 'Upload your Profile Picture':
        img_file_buffer = st.file_uploader('Upload a Picture', type=allowed_image_type)
        if img_file_buffer is not None:
            file_bytes = np.asarray(bytearray(img_file_buffer.read()), dtype=np.uint8)

    elif pic_option == 'Take a Picture with Cam':
        st.info("Ensure only your face is visible to the camera for attendance.")
        tts("Ensure only your face is visible to the camera for attendance.")
        img_file_buffer = st.camera_input("Take a Picture with Cam")
        if img_file_buffer is not None:
            file_bytes = np.frombuffer(img_file_buffer.getvalue(), np.uint8)

    if ((img_file_buffer is not None) & (len(face_name) > 1) & st.button('Image Preview', use_container_width=True)):
        tts("Previewing image")
        st.subheader("Image Preview")
        st.image(img_file_buffer)

    if ((img_file_buffer is not None) & (len(face_name) > 1) & (len(email) > 1) & st.button('Click to Save!', use_container_width=True)):
        conn = connect_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM visitors WHERE Email=?", (email,))
        email_count = cursor.fetchone()[0]
        conn.close()

        if email_count > 0:
            st.error("This email is already associated with another person. Please enter a different email.")
            return

        unique_id = generate_workplace_id(workplace_name)
        image_array = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if image_array is None:
            st.error("Error loading the image. Please try again.")
            return

        with open(os.path.join(VISITOR_DB, f'{face_name}_{unique_id}.jpg'), 'wb') as file:
            file.write(img_file_buffer.getbuffer())
        image_array_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        face_locations, prob = mtcnn(image_array_rgb, return_prob=True)

        if face_locations is None or len(face_locations) == 0:
            st.error("No faces detected in the image. Please try again.")
            st.write("Debugging Info:")
            st.write(f"Image shape: {image_array.shape}")
            st.write(f"Face locations: {face_locations}")
            return

        torch_loc = torch.stack([face_locations[0]]).to(device)
        encodesCurFrame = resnet(torch_loc).detach().cpu()

        df_new = pd.DataFrame(data=encodesCurFrame, columns=COLS_ENCODE)
        df_new['Name'] = face_name
        df_new['Unique_ID'] = unique_id
        df_new['Workplace'] = workplace
        df_new['Job_role'] = job
        df_new['Email'] = email  
        df_new = df_new[['Unique_ID'] + ['Name'] + ['Workplace'] + ['Job_role'] + ['Email'] + COLS_ENCODE].copy()

        add_data_db(df_new)
        email_body = f"Hello {face_name} You are working in {workplace} and your role is {job}"
        send_email(email, "Your Unique ID", email_body, unique_id)
#################################################################################
#################################################################################
### search attendance

def search_attendance():
    st.markdown(f"<h2 style='text-align: center;color:white'>Search Attendance Records</h2>", unsafe_allow_html=True)

    
    # search_type = st.selectbox("Search by", ["Visitor ID", "Name"])
    search_input = st.text_input(f"Enter Visitor ID to search:", '',max_chars=8)

    searchatt = st.button('Search Attendance',use_container_width=True,type='primary')
    clearatt = st.button('Clear Recent Attendance',use_container_width=True,type='secondary')
    if clearatt:
        clearrecenthistory()
    if searchatt:
        df_combined = get_attendance_records()
        search_results = df_combined[df_combined['ID'] == search_input]
        
        # if search_type == "Visitor ID":
        # else:
        #     search_results = df_combined[df_combined['visitor_name'].str.contains(search_input, case=False, na=False)]
        
        if not search_results.empty:
            st.write("### Search Results")
            
            def encode_image(image_path):
                full_image_path = os.path.join(VISITOR_HISTORY, image_path)
                if os.path.isfile(full_image_path):
                    with open(full_image_path, "rb") as image_file:
                        return "data:image/jpeg;base64," + base64.b64encode(image_file.read()).decode()
                return None

            search_results['image'] = search_results['Image_Path'].apply(encode_image)

            try:
                st.data_editor(
                    search_results.drop(columns=["Image_Path"]),
                    column_config={
                        "ID": st.column_config.Column("ID"),
                        "visitor_name": st.column_config.Column("Visitor Name"),
                        "Timing": st.column_config.Column("Timing"),
                        "status":st.column_config.Column("status"),
                        "image": st.column_config.ImageColumn(
                            "Visitor Image", help="Preview of visitor images"
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error displaying search results: {e}")
        else:
            st.warning(f"No records found for Visitor ID: {search_input}")

initialize_db()
###############################################################################
###############################################################################
# Testing 
# with st.sidebar:
#     selection = option_menu("Main Menu", 
#                             ["Take Attendance", "Add Person", "View Attendance", "Search Attendance", 
#                              "Clear Database", "Clear Recent History"], 
#                             icons=["camera", "person-add", "clipboard-data", "search", 
#                                    "trash", "clock-history"], 
#                             menu_icon="cast", 
#                             default_index=0)

# if selection == "Take Attendance":
#     Takeattendance()
# elif selection == "Add Person":
#     personadder()
# elif selection == "View Attendance":
#     view_attendance()
# elif selection == "Search Attendance":
#     search_attendance()  # Adding the search function here
# elif selection == "Clear Database":
#     cleardatabase()
# elif selection == "Clear Recent History":
#     clearrecenthistory()