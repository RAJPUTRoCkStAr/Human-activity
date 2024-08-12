import streamlit as st
import pandas as pd
import numpy as np
from Attendmain import view_attendace,clearrecenthistory
def home():
    view_attendace()
    crh = st.button("clear recent attendance", use_container_width=True, type='primary')
    if crh:
        clearrecenthistory()
    ma = st.button('Monitor Activity', use_container_width=True, type='primary')
    if ma:
        st.write('Monitor button clicked')

