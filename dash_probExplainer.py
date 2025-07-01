import dash
from dash import dcc, html, Input, Output, State, ALL
import dash_bootstrap_components as dbc
import base64
import json
import logging
import warnings
from dash.exceptions import PreventUpdate
import pandas as pd
from pgmpy.readwrite import BIFReader

import pyAgrum as gum
import os
import sys
import tempfile

# Add parent directory to sys.path to resolve imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import session management components (absolute imports)
try:
    from dash_session_manager import start_session_manager, get_session_manager
    from dash_session_components import create_session_components, setup_session_callbacks, register_long_running_process
    SESSION_MANAGEMENT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Session management not available: {e}")
    SESSION_MANAGEMENT_AVAILABLE = False
    # Define dummy functions to prevent errors
    def start_session_manager(): pass
    def get_session_manager(): return None
    def create_session_components(): return None, html.Div()
    def setup_session_callbacks(app): pass
    def register_long_running_process(session_id): pass

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Start the global session manager
if SESSION_MANAGEMENT_AVAILABLE:
    start_session_manager()

# ---------- (1) CREATE DASH APP ---------- #
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        'https://bayes-interpret.com/Evidence/ProbExplainerDash/assets/liquid-glass.css'  # Apple Liquid Glass CSS
    ],
    requests_pathname_prefix='/Evidence/ProbExplainerDash/',
    suppress_callback_exceptions=True
)

server = app.server

# Create session components - but use dynamic session creation
if SESSION_MANAGEMENT_AVAILABLE:
    # Don't create session here - will be created dynamically per user
    session_components = html.Div([
        # Dynamic session store - will be populated by callback
        dcc.Store(id='session-id-store', data=None),
        dcc.Store(id='heartbeat-counter', data=0),
        
        # Interval component for heartbeat (every 5 seconds)
        dcc.Interval(
            id='heartbeat-interval',
            interval=5*1000,  # 5 seconds
            n_intervals=0,
            disabled=False
        ),
        
        # Interval for cleanup check (every 30 seconds)
        dcc.Interval(
            id='cleanup-interval', 
            interval=30*1000,  # 30 seconds
            n_intervals=0,
            disabled=False
        ),
        
        # Hidden div for status
        html.Div(id='session-status', style={'display': 'none'}),
        
        # Client-side script for session management
        html.Script("""
            // Generate unique session ID per browser
            if (!window.dashSessionId) {
                window.dashSessionId = 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
            }
            
            // Send heartbeat on page activity
            document.addEventListener('click', function() {
                if (window.dashHeartbeat) window.dashHeartbeat();
            });
            
            document.addEventListener('keypress', function() {
                if (window.dashHeartbeat) window.dashHeartbeat();
            });
            
            // Handle page unload
            window.addEventListener('beforeunload', function() {
                if (navigator.sendBeacon) {
                    navigator.sendBeacon('/dash/_disconnect', JSON.stringify({
                        session_id: window.dashSessionId
                    }));
                }
            });
            
            // Handle iframe unload (when parent page changes)
            if (window.parent !== window) {
                try {
                    window.parent.addEventListener('beforeunload', function() {
                        if (navigator.sendBeacon) {
                            navigator.sendBeacon('/dash/_disconnect', JSON.stringify({
                                session_id: window.dashSessionId
                            }));
                        }
                    });
                } catch(e) {
                    console.log('Cross-origin iframe detected');
                }
            }
        """),
    ], style={'display': 'none'})
    session_id = None  # Will be set dynamically
else:
    session_id = None
    session_components = html.Div()


# ---------- (2) HELPER FUNCTION FOR pyAgrum PARSING FROM STRING ---------- #
def loadBNfromMemory(bif_string):
    """
    Workaround for pyAgrum versions that do NOT have loadBNFromString.
    We write 'bif_string' into a temp .bif file, then load it.
    """
    with tempfile.NamedTemporaryFile(suffix=".bif", delete=False, mode='w') as tmp:
        tmp_name = tmp.name
        tmp.write(bif_string)
    try:
        bn = gum.loadBN(tmp_name)
    finally:
        # Clean up the temp file
        os.remove(tmp_name)
    return bn


# ---------- (3) APP LAYOUT ---------- #
app.layout = html.Div([
    # SESSION MANAGEMENT COMPONENTS - ADD THESE TO ALL DASH APPS
    session_components,
    
    dcc.Loading(
        id="global-spinner",
        type="default",
        fullscreen=False,
        color="#00A2E1",
        style={
            "position": "fixed",
            "top": "50%",
            "left": "50%",
            "transform": "translate(-50%, -50%)",
            "zIndex": "999999"
        },
        children=html.Div([
            html.H1("Bayesian Network ProbExplainer ", style={'textAlign': 'center'}),

            ########################################################
            # Info text
            ########################################################
            html.Div(
                className="link-bar",
                style={
                    "textAlign": "center",
                    "marginBottom": "20px"
                },
                children=[
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/github.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Original GitHub"
                        ],
                        href="https://github.com/Enrique-Val/ProbExplainer",
                        target="_blank",
                        className="btn btn-outline-info me-2"
                    ),
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/2023/11/cropped-logo_CIG.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Paper PDF"
                        ],
                        href="https://cig.fi.upm.es/wp-content/uploads/2024/01/Efficient-search-for-relevance-explanations-using-MAP-independence-in-Bayesian-networks.pdf",
                        target="_blank",
                        className="btn btn-outline-primary me-2"
                    ),
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/github.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Dash Adapted GitHub"
                        ],
                        href="https://github.com/KeevinPR/ProbExplainer",
                        target="_blank",
                        className="btn btn-outline-info me-2"
                    ),
                ]
            ),
            ########################################################
            # Short explanatory text
            ########################################################
            html.Div(
                [
                    html.P(
                        "Library to adapt and explain probabilistic models and specially aimed for Bayesian networks.",
                        style={"textAlign": "center", "maxWidth": "800px", "margin": "0 auto"}
                    )
                ],
                style={"marginBottom": "20px"}
            ),

            ########################################################
            # (A) Data upload
            ########################################################
            html.Div(className="card", children=[
                html.H3("1. Upload Dataset", style={'textAlign': 'center'}),

                # Container "card"
                html.Div([
                    # Top part with icon and text
                    html.Div([
                        html.Img(
                            src="https://img.icons8.com/ios-glyphs/40/cloud--v1.png",
                            className="upload-icon"
                        ),
                        html.Div("Drag and drop or select a CSV/BIF file", className="upload-text")
                    ]),
                    
                    # Upload component
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([], style={'display': 'none'}),
                        className="upload-dropzone",
                        multiple=False
                    ),
                ], className="upload-card"),

                # Use default dataset + help icon
                html.Div([
                    dcc.Checklist(
                        id='use-default-network',
                        options=[{'label': 'Use the default dataset', 'value': 'default'}],
                        value=[],
                        style={'display': 'inline-block', 'textAlign': 'center', 'marginTop': '10px'}
                    ),
                    dbc.Button(
                        html.I(className="fa fa-question-circle"),
                        id="help-button-default-dataset",
                        color="link",
                        style={"display": "inline-block", "marginLeft": "8px"}
                    ),
                ], style={'textAlign': 'center'}),
            ]),

            # Section to select action
            html.Div(className="card", children=[
                html.H3("2. Select an Action to Perform", style={'textAlign': 'center'}),
                html.Div([
                    dbc.Select(
                        id='action-dropdown',
                        options=[
                            {'label': 'Compute Posterior', 'value': 'posterior'},
                            {'label': 'Map Independence', 'value': 'map_independence'},
                            {'label': 'Get Defeaters', 'value': 'defeaters'}
                        ],
                        value='posterior',  # Default action
                        style={
                            'width': '100%',
                            'border': '1px solid #d0d7de',
                            'borderRadius': '6px',
                            'padding': '8px 12px',
                            'backgroundColor': 'rgba(255, 255, 255, 0.8)',
                            'backdropFilter': 'blur(10px)',
                            'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                            'transition': 'all 0.2s ease',
                            'fontSize': '14px'
                        }
                    )
                ], style={'width': '300px', 'margin': '0 auto'})
            ]),

            # Evidence selection
            html.Div(className="card", children=[
                html.Div([
                    html.H3("3. Select Evidence Variables", style={'display': 'inline-block', 'marginRight': '10px', 'textAlign': 'center'}),
                    dbc.Button(
                        html.I(className="fa fa-question-circle"),
                        id="help-button-evidence",
                        color="link",
                        style={"display": "inline-block", "verticalAlign": "middle", "padding": "0", "marginLeft": "5px"}
                    ),
                ], style={"textAlign": "center", "position": "relative"}),
                
                # Buttons for bulk selection
                html.Div([
                    dbc.Button(
                        "Select All",
                        id="select-all-evidence",
                        color="outline-primary",
                        size="sm",
                        style={'marginRight': '10px'}
                    ),
                    dbc.Button(
                        "Clear All",
                        id="clear-evidence",
                        color="outline-secondary",
                        size="sm"
                    )
                ], style={'textAlign': 'center', 'marginBottom': '15px'}),
                
                # Checkbox container for evidence variables
                html.Div(
                    id='evidence-checkbox-container',
                    style={
                        'maxHeight': '200px',
                        'overflowY': 'auto',
                        'border': '1px solid #ddd',
                        'borderRadius': '5px',
                        'padding': '10px',
                        'margin': '0 auto',
                        'width': '80%',
                        'backgroundColor': '#f8f9fa'
                    }
                ),
                
                html.Div(id='evidence-values-container')
            ]),

            # Target variables
            html.Div(className="card", children=[
                html.Div([
                    html.H3("4. Select Target Variables", style={'display': 'inline-block', 'marginRight': '10px', 'textAlign': 'center'}),
                    dbc.Button(
                        html.I(className="fa fa-question-circle"),
                        id="help-button-targets",
                        color="link",
                        style={"display": "inline-block", "verticalAlign": "middle", "padding": "0", "marginLeft": "5px"}
                    ),
                ], style={"textAlign": "center", "position": "relative"}),
                
                # Buttons for bulk selection
                html.Div([
                    dbc.Button(
                        "Select All",
                        id="select-all-targets",
                        color="outline-primary",
                        size="sm",
                        style={'marginRight': '10px'}
                    ),
                    dbc.Button(
                        "Clear All",
                        id="clear-targets",
                        color="outline-secondary",
                        size="sm"
                    )
                ], style={'textAlign': 'center', 'marginBottom': '15px'}),
                
                # Checkbox container for target variables
                html.Div(
                    id='target-checkbox-container',
                    style={
                        'maxHeight': '200px',
                        'overflowY': 'auto',
                        'border': '1px solid #ddd',
                        'borderRadius': '5px',
                        'padding': '10px',
                        'margin': '0 auto',
                        'width': '80%',
                        'backgroundColor': '#f8f9fa'
                    }
                ),
                
                # Info message about intelligent selection
                html.Div([
                    html.I(className="fa fa-info-circle", style={'marginRight': '5px', 'color': '#6c757d'}),
                    html.Span("Target variables automatically exclude evidence variables. Previous selections are preserved when possible.", 
                             style={'fontSize': '11px', 'color': '#6c757d'})
                ], style={'textAlign': 'center', 'marginTop': '8px'}),
            ]),

            # Set R (only needed for map_independence)
            html.Div(className="card", children=[
                html.Div([
                    html.H3("5. Select Set R (only for Map Independence)", style={'display': 'inline-block', 'marginRight': '10px', 'textAlign': 'center'}),
                    dbc.Button(
                        html.I(className="fa fa-question-circle"),
                        id="help-button-r-vars",
                        color="link",
                        style={"display": "inline-block", "verticalAlign": "middle", "padding": "0", "marginLeft": "5px"}
                    ),
                ], style={"textAlign": "center", "position": "relative"}),
                
                # Buttons for bulk selection
                html.Div([
                    dbc.Button(
                        "Select All",
                        id="select-all-r-vars",
                        color="outline-primary",
                        size="sm",
                        style={'marginRight': '10px'}
                    ),
                    dbc.Button(
                        "Clear All",
                        id="clear-r-vars",
                        color="outline-secondary",
                        size="sm"
                    )
                ], style={'textAlign': 'center', 'marginBottom': '15px'}),
                
                # Checkbox container for R variables
                html.Div(
                    id='r-vars-checkbox-container',
                    style={
                        'maxHeight': '200px',
                        'overflowY': 'auto',
                        'border': '1px solid #ddd',
                        'borderRadius': '5px',
                        'padding': '10px',
                        'margin': '0 auto',
                        'width': '80%',
                        'backgroundColor': '#f8f9fa'
                    }
                ),
                
                # Info message about R set selection
                html.Div([
                    html.I(className="fa fa-info-circle", style={'marginRight': '5px', 'color': '#6c757d'}),
                    html.Span("R variables exclude both evidence and target variables.", 
                             style={'fontSize': '11px', 'color': '#6c757d'})
                ], style={'textAlign': 'center', 'marginTop': '8px'}),
            ]),

            # Run button
            html.Div([
                dbc.Button(
                    [
                        html.I(className="fas fa-play-circle me-2"),
                        "Run Analysis"
                    ],
                    id='run-action-button',
                    n_clicks=0,
                    color="info",
                    className="btn-lg",
                    style={
                        'fontSize': '1.1rem',
                        'padding': '0.75rem 2rem',
                        'borderRadius': '8px',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                        'transition': 'all 0.3s ease',
                        'backgroundColor': '#00A2E1',
                        'border': 'none',
                        'margin': '1rem 0',
                        'color': 'white',
                        'fontWeight': '500'
                    }
                )
            ], style={'textAlign': 'center'}),
            html.Br(),
            html.Div(id='action-results', style={'textAlign': 'center'}),

            # Store to keep the chosen network path/string
            dcc.Store(id='stored-network'),

            # Store to keep the nodes and states (so we don't parse repeatedly)
            dcc.Store(id='stored-model-info'),
            
            # Stores for tracking selections
            dcc.Store(id='previous-evidence-selection', data=[]),
            dcc.Store(id='previous-target-selection', data=[]),
            dcc.Store(id='previous-r-selection', data=[]),
            
            # Store to detect dataset changes and trigger reset
            dcc.Store(id='dataset-change-detector', data=None),
            
            # Store for tracking clean state
            dcc.Store(id='app-clean-state', data=True),
            
            # Notification system
            dcc.Store(id='notification-store'),
        ])
    ),
    dbc.Popover(
        [
            dbc.PopoverHeader(
                [
                    "Help",
                    html.I(className="fa fa-info-circle ms-2", style={"color": "#0d6efd"})
                ],
                style={
                    "backgroundColor": "#f8f9fa",  # Light gray background
                    "fontWeight": "bold"
                }
            ),
            dbc.PopoverBody(
                [
                    html.P(
                        [
                            "For details and content of the dataset, check out: ",
                            html.A(
                                "network_5.bif",
                                href="https://github.com/KeevinPR/ProbExplainer/blob/main/expert_networks/network_5.bif",
                                target="_blank",
                                style={"textDecoration": "underline", "color": "#0d6efd"}
                            ),
                        ]
                    ),
                    html.Hr(),  # Horizontal rule for a modern divider
                    html.P("Feel free to upload your own dataset at any time.")
                ],
                style={
                    "backgroundColor": "#ffffff",
                    "borderRadius": "0 0 0.25rem 0.25rem"
                }
            ),
        ],
        id="help-popover-default-dataset",
        target="help-button-default-dataset",
        placement="right",
        is_open=False,
        trigger="hover"
    ),
    
    # Add Evidence Selection Popover
    dbc.Popover(
        [
            dbc.PopoverHeader(
                [
                    "Evidence Selection",
                    html.I(className="fa fa-info-circle ms-2", style={"color": "#0d6efd"})
                ],
                style={"backgroundColor": "#f8f9fa", "fontWeight": "bold"}
            ),
            dbc.PopoverBody(
                [
                    html.P("Evidence variables are the known states in your Bayesian network."),
                    html.P("Select one or more variables that you want to use as evidence."),
                    html.P("For each selected variable, you'll need to specify its state."),
                    html.P("These values will be used in the probabilistic analysis."),
                ],
                style={"backgroundColor": "#ffffff", "borderRadius": "0 0 0.25rem 0.25rem", "maxWidth": "300px"}
            ),
        ],
        id="help-popover-evidence",
        target="help-button-evidence",
        placement="right",
        is_open=False,
        trigger="hover",
        style={"position": "absolute", "zIndex": 1000, "marginLeft": "5px"}
    ),

    # Add Target Variables Popover
    dbc.Popover(
        [
            dbc.PopoverHeader(
                [
                    "Target Variables",
                    html.I(className="fa fa-info-circle ms-2", style={"color": "#0d6efd"})
                ],
                style={"backgroundColor": "#f8f9fa", "fontWeight": "bold"}
            ),
            dbc.PopoverBody(
                [
                    html.P("Target variables are the nodes you want to analyze in your Bayesian network."),
                    html.P("Select one or more variables for your analysis:"),
                    html.Ul([
                        html.Li("Compute Posterior: Variables to compute probabilities for"),
                        html.Li("Map Independence: Variables for MAP estimation"),
                        html.Li("Get Defeaters: Variables to find defeaters for")
                    ]),
                    html.P("Variables used as evidence cannot be selected as targets."),
                ],
                style={"backgroundColor": "#ffffff", "borderRadius": "0 0 0.25rem 0.25rem", "maxWidth": "300px"}
            ),
        ],
        id="help-popover-targets",
        target="help-button-targets",
        placement="right",
        is_open=False,
        trigger="hover",
        style={"position": "absolute", "zIndex": 1000, "marginLeft": "5px"}
    ),

    # Add R Variables Popover
    dbc.Popover(
        [
            dbc.PopoverHeader(
                [
                    "Set R Variables",
                    html.I(className="fa fa-info-circle ms-2", style={"color": "#0d6efd"})
                ],
                style={"backgroundColor": "#f8f9fa", "fontWeight": "bold"}
            ),
            dbc.PopoverBody(
                [
                    html.P("Set R is only used for Map Independence analysis."),
                    html.P("These variables represent the intervention set for testing independence."),
                    html.P("The analysis will check if the MAP assignment is independent of interventions on these variables."),
                    html.P("R variables exclude both evidence and target variables."),
                ],
                style={"backgroundColor": "#ffffff", "borderRadius": "0 0 0.25rem 0.25rem", "maxWidth": "300px"}
            ),
        ],
        id="help-popover-r-vars",
        target="help-button-r-vars",
        placement="right",
        is_open=False,
        trigger="hover",
        style={"position": "absolute", "zIndex": 1000, "marginLeft": "5px"}
    ),
    
    # Notification container (outside dcc.Loading to avoid interference)
    html.Div(id='notification-container', style={
        'position': 'fixed',
        'bottom': '20px',
        'right': '20px',
        'zIndex': '1000',
        'width': '300px',
        'transition': 'all 0.3s ease-in-out',
        'transform': 'translateY(100%)',
        'opacity': '0'
    }),
])


# ---------- (4) CALLBACKS ---------- #

# (A) Checking the "Use default" => clear uploaded file contents and let main callback handle default
@app.callback(
    Output('upload-data', 'contents'),
    Input('use-default-network', 'value'),
    prevent_initial_call=True
)
def clear_upload_when_default_selected(value):
    """
    When default is selected, clear any uploaded file to avoid conflicts.
    The main load_network callback will handle the default loading logic.
    """
    if 'default' in value:
        # Clear the upload contents so default takes precedence
        logger.info("Default selected, clearing uploaded file")
        return None
    return dash.no_update


# (B) Store the chosen network (default or uploaded) in 'stored-network'
@app.callback(
    Output('stored-network', 'data'),
    Output('notification-store', 'data'),
    Output('dataset-change-detector', 'data'),
    Output('use-default-network', 'value'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    Input('use-default-network', 'value')
)
def load_network(contents, filename, default_value):
    """
    Store path/string in 'stored-network' and provide user feedback via notifications.
    Also manages dataset change detection and checkbox state.
    
    - If 'default' is in default_value => use the known path to network_5.bif (or your default).
    - If user uploads => decode the BIF string and uncheck default.
    - If nothing => PreventUpdate.
    """
    import time
    
    # Generate unique change ID for dataset change detection
    change_id = str(time.time())
    
    # Priority 1: Handle file upload (takes precedence over default)
    if contents:
        logger.info(f"Attempting to load uploaded network: {filename}")
        
        # Validate file extension
        if filename and not filename.lower().endswith('.bif'):
            return dash.no_update, create_warning_notification(
                "Please upload a .bif file. Other formats are not supported.",
                "Invalid File Format"
            ), dash.no_update, default_value
        
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            bif_data = decoded.decode('utf-8')
            
            # Check if valid BIF with pgmpy
            reader_check = BIFReader(string=bif_data)
            model = reader_check.get_model()  # fails if invalid
            
            # Additional validations
            if not model.nodes():
                return dash.no_update, create_error_notification(
                    "The uploaded network has no nodes. Please check your BIF file.",
                    "Empty Network"
                ), dash.no_update, default_value
                
            node_count = len(model.nodes())
            if node_count > 100:
                network_data = {
                    'network_name': filename,
                    'network_type': 'string',
                    'content': bif_data
                }
                notification = create_warning_notification(
                    f"Large network detected ({node_count} nodes). Performance may be affected.",
                    "Large Network"
                )
                # Clear default checkbox when file is uploaded
                return network_data, notification, change_id, []
            
            logger.info(f"Valid network uploaded: {filename} with {node_count} nodes")
            network_data = {
                'network_name': filename,
                'network_type': 'string',
                'content': bif_data
            }
            # Clear default checkbox when file is uploaded successfully
            return network_data, None, change_id, []
            
        except UnicodeDecodeError:
            logger.error(f"Error decoding file: {filename}")
            return dash.no_update, create_error_notification(
                "Unable to decode the file. Please ensure it's a valid text-based BIF file.",
                "File Encoding Error"
            ), dash.no_update, default_value
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error loading network: {e}")
            
            # Provide specific error messages for common issues
            if "variable" in error_msg.lower() and "not found" in error_msg.lower():
                notification = create_error_notification(
                    "Network contains undefined variables. Please check your BIF file structure.",
                    "Invalid Network Structure"
                )
            elif "probability" in error_msg.lower():
                notification = create_error_notification(
                    "Network contains invalid probability values. Please verify your CPTs.",
                    "Invalid Probabilities"
                )
            elif "parse" in error_msg.lower() or "syntax" in error_msg.lower():
                notification = create_error_notification(
                    "BIF file has syntax errors. Please check the file format.",
                    "Syntax Error"
                )
            else:
                notification = create_error_notification(
                    f"Error loading network: {error_msg}",
                    "Network Loading Error"
                )
            return dash.no_update, notification, dash.no_update, default_value

    # Priority 2: Handle default checkbox (only if no file was uploaded)
    elif 'default' in default_value:
        try:
            # Check if default file exists and is valid
            default_path = '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/ProbExplainer/expert_networks/network_5.bif'
            
            # Validate default file
            with open(default_path, 'r') as f:
                default_data = f.read()
            test_reader = BIFReader(string=default_data)
            _ = test_reader.get_model()  # Validate structure
            
            logger.info("Using default network: network_5.bif")
            network_data = {
                'network_name': 'network_5.bif',
                'network_type': 'path',
                'content': default_path
            }
            # Keep default checkbox checked
            return network_data, None, change_id, default_value
        except FileNotFoundError:
            logger.error("Default network file not found")
            return dash.no_update, create_error_notification(
                "Default network file not found. Please upload your own BIF file.",
                "File Not Found"
            ), dash.no_update, default_value
        except Exception as e:
            logger.error(f"Error loading default network: {e}")
            return dash.no_update, create_error_notification(
                f"Error loading default network: {str(e)}",
                "Invalid Default Network"
            ), dash.no_update, default_value

    # If neither default is checked nor any file is uploaded => do nothing
    raise PreventUpdate


# (B.5) Reset app state when dataset changes
@app.callback(
    Output('action-results', 'children', allow_duplicate=True),
    Output('app-clean-state', 'data'),
    Output('previous-evidence-selection', 'data', allow_duplicate=True),
    Output('previous-target-selection', 'data', allow_duplicate=True), 
    Output('previous-r-selection', 'data', allow_duplicate=True),
    Output('notification-store', 'data', allow_duplicate=True),
    Input('dataset-change-detector', 'data'),
    prevent_initial_call=True
)
def reset_app_state_on_dataset_change(change_id):
    """
    Reset app to clean state when dataset changes.
    This clears previous results and selections to avoid confusion.
    """
    if change_id is not None:
        logger.info(f"Dataset changed (ID: {change_id}), resetting app state")
        
        # Create notification to inform user of reset
        notification = create_info_notification(
            "Application state has been reset due to dataset change. Previous selections and results have been cleared.",
            "State Reset"
        )
        
        return (
            html.Div(),  # Clear action results
            True,        # Mark app as clean
            [],          # Clear previous evidence selection
            [],          # Clear previous target selection
            [],          # Clear previous R selection
            notification # Notify user of reset
        )
    raise PreventUpdate


# (B.6) Clear checkboxes when dataset changes
@app.callback(
    Output({'type': 'evidence-checkbox', 'index': ALL}, 'value', allow_duplicate=True),
    Output({'type': 'target-checkbox', 'index': ALL}, 'value', allow_duplicate=True),
    Output({'type': 'r-vars-checkbox', 'index': ALL}, 'value', allow_duplicate=True),
    Input('dataset-change-detector', 'data'),
    State({'type': 'evidence-checkbox', 'index': ALL}, 'id'),
    State({'type': 'target-checkbox', 'index': ALL}, 'id'),
    State({'type': 'r-vars-checkbox', 'index': ALL}, 'id'),
    prevent_initial_call=True
)
def clear_checkboxes_on_dataset_change(change_id, evidence_ids, target_ids, r_vars_ids):
    """
    Clear all checkbox selections when dataset changes to start fresh.
    """
    if change_id is not None:
        logger.info("Clearing all checkbox selections due to dataset change")
        # Return empty lists for all checkboxes to clear them
        evidence_clear = [[] for _ in evidence_ids]
        target_clear = [[] for _ in target_ids] 
        r_vars_clear = [[] for _ in r_vars_ids]
        return evidence_clear, target_clear, r_vars_clear
    raise PreventUpdate


# (B.7) Clear evidence values container when dataset changes
@app.callback(
    Output('evidence-values-container', 'children', allow_duplicate=True),
    Input('dataset-change-detector', 'data'),
    prevent_initial_call=True
)
def clear_evidence_values_on_dataset_change(change_id):
    """
    Clear evidence values dropdowns when dataset changes.
    """
    if change_id is not None:
        logger.info("Clearing evidence values container due to dataset change")
        return []
    raise PreventUpdate


# (C) Once 'stored-network' is set, parse it with pgmpy => store nodes/states in 'stored-model-info'
@app.callback(
    Output('stored-model-info', 'data'),
    Output('notification-store', 'data', allow_duplicate=True),
    Input('stored-network', 'data'),
    prevent_initial_call=True
)
def parse_network_and_store_info(stored_net):
    if not stored_net:
        raise PreventUpdate

    logger.info("Parsing network with pgmpy to extract nodes/states...")
    try:
        if stored_net['network_type'] == 'path':
            reader_local = BIFReader(stored_net['content'])
        else:
            # read from string
            reader_local = BIFReader(string=stored_net['content'])

        net = reader_local.get_model()
        nodes_list = sorted(net.nodes())

        # Validate network structure
        if not nodes_list:
            logger.error("Network has no nodes")
            return dash.no_update, create_error_notification(
                "The network has no nodes. Please check your BIF file.",
                "Empty Network"
            )

        # For each node, gather possible states and validate:
        states_dict = {}
        problematic_nodes = []
        
        for var in nodes_list:
            try:
                cpd = net.get_cpds(var)
                states = cpd.state_names[var]
                
                # Validate states
                if not states or len(states) == 0:
                    problematic_nodes.append(f"{var} (no states)")
                elif len(states) == 1:
                    logger.warning(f"Node {var} has only one state: {states[0]}")
                
                states_dict[var] = states
            except Exception as e:
                logger.error(f"Error processing node {var}: {e}")
                problematic_nodes.append(f"{var} (processing error)")

        # Report warnings for problematic nodes
        if problematic_nodes:
            warning_msg = f"Some nodes have issues: {', '.join(problematic_nodes[:3])}"
            if len(problematic_nodes) > 3:
                warning_msg += f" and {len(problematic_nodes) - 3} more"
            
            return {
                'nodes': nodes_list,
                'states': states_dict
            }, create_warning_notification(
                warning_msg,
                "Network Structure Issues"
            )

        # Success case - no notification needed
        return {
            'nodes': nodes_list,
            'states': states_dict
        }, None
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error parsing network in parse_network_and_store_info: {e}")
        
        # Provide specific error messages
        if "file not found" in error_msg.lower():
            return dash.no_update, create_error_notification(
                "Network file not found. Please re-upload your BIF file.",
                "File Not Found"
            )
        elif "permission" in error_msg.lower():
            return dash.no_update, create_error_notification(
                "Permission denied accessing network file. Please try uploading again.",
                "Access Error"
            )
        else:
            return dash.no_update, create_error_notification(
                f"Failed to parse network: {error_msg}",
                "Parsing Error"
            )


# (D) Populate evidence checkbox container only if a model is available
@app.callback(
    Output('evidence-checkbox-container', 'children'),
    Input('stored-model-info', 'data')
)
def update_evidence_variables(model_info):
    if not model_info:
        return html.Div("No network loaded", style={'textAlign': 'center', 'color': '#666'})
    
    variables = model_info['nodes']
    if not variables:
        return html.Div("No variables found", style={'textAlign': 'center', 'color': '#666'})
    
    # Create checkboxes in a grid layout
    checkboxes = []
    for i, var in enumerate(variables):
        checkboxes.append(
            html.Div([
                dcc.Checklist(
                    id={'type': 'evidence-checkbox', 'index': var},
                    options=[{'label': f' {var}', 'value': var}],
                    value=[],
                    style={'margin': '0'}
                )
            ], style={'display': 'inline-block', 'width': '50%', 'marginBottom': '5px'})
        )
    
    return html.Div(checkboxes, style={'columnCount': '2', 'columnGap': '20px'})

# Build the dynamic evidence-value dropdowns
@app.callback(
    Output('evidence-values-container', 'children'),
    Input({'type': 'evidence-checkbox', 'index': ALL}, 'value'),
    State('stored-model-info', 'data')
)
def update_evidence_values(checkbox_values, model_info):
    # Get selected evidence variables from checkboxes
    ctx = dash.callback_context
    if not ctx.inputs:
        return []
    
    # Extract selected variables
    evidence_vars = []
    for input_info in ctx.inputs_list[0]:
        if input_info['value']:  # If checkbox is checked
            var_name = input_info['id']['index']
            evidence_vars.append(var_name)
    
    if not evidence_vars or not model_info:
        return []

    states_dict = model_info['states']  # var -> list_of_states
    children = []
    for var in evidence_vars:
        var_states = states_dict.get(var, [])
        children.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Label(
                                f"Select value for {var}",
                                style={'width': '40%', 'textAlign': 'right', 'paddingRight': '10px'}
                            ),
                            dbc.Select(
                                id={'type': 'evidence-value-dropdown', 'index': var},
                                options=[{'label': s, 'value': s} for s in var_states],
                                value=var_states[0] if var_states else None,
                                style={
                                    'width': '60%',
                                    'border': '1px solid #d0d7de',
                                    'borderRadius': '6px',
                                    'padding': '8px 12px',
                                    'backgroundColor': 'rgba(255, 255, 255, 0.8)',
                                    'backdropFilter': 'blur(10px)',
                                    'boxShadow': '0 1px 3px rgba(0, 0, 0, 0.1)',
                                    'transition': 'all 0.2s ease',
                                    'fontSize': '14px'
                                }
                            )
                        ],
                        style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}
                    )
                ],
                style={'marginBottom': '10px', 'width': '50%', 'margin': '0 auto'}
            )
        )
    return children

# Populate target variables, excluding those in evidence
@app.callback(
    Output('target-checkbox-container', 'children'),
    Output('previous-evidence-selection', 'data'),
    Input({'type': 'evidence-checkbox', 'index': ALL}, 'value'),
    State('stored-model-info', 'data'),
    State('previous-evidence-selection', 'data'),
    State('previous-target-selection', 'data')
)
def update_target_options(checkbox_values, model_info, prev_evidence, prev_targets):
    if not model_info:
        return html.Div("No network loaded", style={'textAlign': 'center', 'color': '#666'}), []
    
    # Get currently selected evidence variables from checkboxes
    current_evidence = []
    ctx = dash.callback_context
    if ctx.inputs_list and ctx.inputs_list[0]:
        for input_info in ctx.inputs_list[0]:
            if input_info['value']:  # If checkbox is checked
                var_name = input_info['id']['index']
                current_evidence.append(var_name)
    
    all_vars = set(model_info['nodes'])
    available = [v for v in all_vars if v not in current_evidence]

    if not available:
        return html.Div("No target variables available", style={'textAlign': 'center', 'color': '#666'}), current_evidence
    
    # Calculate which targets should remain selected:
    # 1. Variables that were targets before and are still available
    # 2. Variables that were removed from evidence and were targets before
    newly_available = set(prev_evidence) - set(current_evidence)  # Variables removed from evidence
    keep_selected = (set(prev_targets) & set(available)) | (newly_available & set(prev_targets))
    
    # Create checkboxes in a grid layout
    checkboxes = []
    for var in available:
        # Pre-select if it should remain selected
        initial_value = [var] if var in keep_selected else []
        
        checkboxes.append(
            html.Div([
                dcc.Checklist(
                    id={'type': 'target-checkbox', 'index': var},
                    options=[{'label': f' {var}', 'value': var}],
                    value=initial_value,
                    style={'margin': '0'}
                )
            ], style={'display': 'inline-block', 'width': '50%', 'marginBottom': '5px'})
        )
    
    return html.Div(checkboxes, style={'columnCount': '2', 'columnGap': '20px'}), current_evidence

# Callback to track target selections for intelligent management
@app.callback(
    Output('previous-target-selection', 'data'),
    Input({'type': 'target-checkbox', 'index': ALL}, 'value')
)
def track_target_selections(target_checkbox_values):
    """Track which targets are currently selected"""
    selected_targets = []
    for checkbox_value in target_checkbox_values or []:
        if checkbox_value:  # If checkbox is checked
            selected_targets.extend(checkbox_value)
    return selected_targets

# Populate R variables, excluding evidence and targets
@app.callback(
    Output('r-vars-checkbox-container', 'children'),
    Output('previous-r-selection', 'data'),
    Input({'type': 'evidence-checkbox', 'index': ALL}, 'value'),
    Input({'type': 'target-checkbox', 'index': ALL}, 'value'),
    State('stored-model-info', 'data'),
    State('previous-r-selection', 'data')
)
def update_r_vars_options(evidence_checkbox_values, target_checkbox_values, model_info, prev_r_vars):
    if not model_info:
        return html.Div("No network loaded", style={'textAlign': 'center', 'color': '#666'}), []
    
    # Get currently selected evidence and target variables
    current_evidence = []
    current_targets = []
    
    ctx = dash.callback_context
    if ctx.inputs_list:
        # Process evidence checkboxes
        for input_info in ctx.inputs_list[0]:
            if input_info['value']:
                var_name = input_info['id']['index']
                current_evidence.append(var_name)
        
        # Process target checkboxes
        for input_info in ctx.inputs_list[1]:
            if input_info['value']:
                var_name = input_info['id']['index']
                current_targets.append(var_name)
    
    all_vars = set(model_info['nodes'])
    excluded = set(current_evidence) | set(current_targets)
    available = [v for v in all_vars if v not in excluded]
    
    if not available:
        return html.Div("No R variables available", style={'textAlign': 'center', 'color': '#666'}), []
    
    # Keep previously selected R variables that are still available
    keep_selected = set(prev_r_vars) & set(available)
    
    # Create checkboxes in a grid layout
    checkboxes = []
    for var in available:
        initial_value = [var] if var in keep_selected else []
        
        checkboxes.append(
            html.Div([
                dcc.Checklist(
                    id={'type': 'r-vars-checkbox', 'index': var},
                    options=[{'label': f' {var}', 'value': var}],
                    value=initial_value,
                    style={'margin': '0'}
                )
            ], style={'display': 'inline-block', 'width': '50%', 'marginBottom': '5px'})
        )
    
    # Track current R selection
    current_r = []
    for checkbox_value in checkboxes:
        # This is just for initialization, actual tracking happens in separate callback
        pass
    
    return html.Div(checkboxes, style={'columnCount': '2', 'columnGap': '20px'}), list(keep_selected)

# Main callback: run the chosen action
@app.callback(
    Output('action-results', 'children'),
    Output('notification-store', 'data', allow_duplicate=True),
    Input('run-action-button', 'n_clicks'),
    State('action-dropdown', 'value'),
    State('stored-network', 'data'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'value'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'id'),
    State({'type': 'target-checkbox', 'index': ALL}, 'value'),
    State({'type': 'r-vars-checkbox', 'index': ALL}, 'value'),
    State('session-id-store', 'data'),
    prevent_initial_call=True
)
def run_action(n_clicks, action, stored_network,
               evidence_values, evidence_ids,
               target_checkbox_values, r_vars_checkbox_values, session_id):
    if not n_clicks:
        raise PreventUpdate
    
    # REGISTER THIS PROCESS WITH SESSION MANAGER (CRITICAL FOR CLEANUP)
    if SESSION_MANAGEMENT_AVAILABLE and session_id:
        register_long_running_process(session_id)
        logger.info(f"Registered ProbExplainer analysis process for session {session_id}")

    # Validate basic requirements
    if not stored_network:
        return html.Div("No network loaded. Please upload or select the default network.", style={'color': 'red'}), create_error_notification(
            "No network loaded. Please upload or select the default network.",
            "Network Required"
        )

    # Build evidence dict with validation
    evidence_dict = {}
    if evidence_values and evidence_ids:
        for ev_id, val in zip(evidence_ids, evidence_values):
            if val is not None:  # ignore if none
                var = ev_id['index']
                evidence_dict[var] = val

    # Extract selected target variables from checkboxes
    target_vars = []
    for checkbox_value in target_checkbox_values:
        if checkbox_value:  # If checkbox is checked, it contains the variable name
            target_vars.extend(checkbox_value)

    # Extract selected R variables from checkboxes
    r_vars = []
    for checkbox_value in r_vars_checkbox_values:
        if checkbox_value:  # If checkbox is checked, it contains the variable name
            r_vars.extend(checkbox_value)

    # Validate configuration based on action
    if action == 'posterior':
        if not target_vars:
            return html.Div("Please select at least one target variable for Compute Posterior.", style={'color': 'red'}), create_error_notification(
                "Please select at least one target variable for Compute Posterior.",
                "Configuration Error"
            )
    elif action == 'map_independence':
        if not target_vars:
            return html.Div("Please select at least one target variable for Map Independence.", style={'color': 'red'}), create_error_notification(
                "Please select at least one target variable for Map Independence.",
                "Configuration Error"
            )
        if not r_vars:
            return html.Div("Please select at least one variable in R for Map Independence.", style={'color': 'red'}), create_error_notification(
                "Please select at least one variable in R for Map Independence.",
                "Configuration Error"
            )
    elif action == 'defeaters':
        if not target_vars:
            return html.Div("Please select at least one target variable for Get Defeaters.", style={'color': 'red'}), create_error_notification(
                "Please select at least one target variable for Get Defeaters.",
                "Configuration Error"
            )

    # Check for variable overlap
    overlap_evidence_targets = set(evidence_dict.keys()) & set(target_vars)
    if overlap_evidence_targets:
        overlap_vars = ', '.join(overlap_evidence_targets)
        return html.Div(f"Variables cannot be both evidence and targets: {overlap_vars}", style={'color': 'red'}), create_error_notification(
            f"Variables cannot be both evidence and targets: {overlap_vars}",
            "Variable Overlap Error"
        )

    if action == 'map_independence':
        overlap_evidence_r = set(evidence_dict.keys()) & set(r_vars)
        overlap_targets_r = set(target_vars) & set(r_vars)
        if overlap_evidence_r or overlap_targets_r:
            overlap_vars = ', '.join(overlap_evidence_r | overlap_targets_r)
            return html.Div(f"R variables cannot overlap with evidence or targets: {overlap_vars}", style={'color': 'red'}), create_error_notification(
                f"R variables cannot overlap with evidence or targets: {overlap_vars}",
                "Variable Overlap Error"
            )

    # Import and validate dependencies
    try:
        from probExplainer.model.BayesianNetwork import BayesianNetworkPyAgrum, ImplausibleEvidenceException
    except ImportError as e:
        return html.Div("ProbExplainer library not found. Please check installation.", style={'color': 'red'}), create_error_notification(
            "ProbExplainer library not found. Please check installation.",
            "Import Error"
        )

    # Load BN with pyAgrum (without loadBNFromString)
    try:
        if stored_network['network_type'] == 'path':
            bn_pya = gum.loadBN(stored_network['content'])
        else:
            # if it's a string => use our helper
            bn_pya = loadBNfromMemory(stored_network['content'])
    except FileNotFoundError:
        return html.Div("Network file not found.", style={'color': 'red'}), create_error_notification(
            "Network file not found. Please re-upload your BIF file.",
            "File Not Found"
        )
    except Exception as e:
        return html.Div(f"Error loading network in pyAgrum: {e}", style={'color': 'red'}), create_error_notification(
            f"Error loading network in pyAgrum: {str(e)}",
            "Network Loading Error"
        )

    # Create adapter
    try:
        bn_adapter = BayesianNetworkPyAgrum(bn_pya)
    except Exception as e:
        return html.Div(f"Error creating BayesianNetworkPyAgrum: {e}", style={'color': 'red'}), create_error_notification(
            f"Error creating network adapter: {str(e)}",
            "Adapter Error"
        )

    # Perform chosen action with comprehensive error handling
    try:
        if action == 'posterior':
            logger.info(f"Computing posterior for targets: {target_vars}, evidence: {evidence_dict}")
            
            # Validate evidence values exist in network
            invalid_evidence = []
            for var, val in evidence_dict.items():
                if var in bn_pya.names():
                    possible_states = [str(s) for s in bn_pya.variable(bn_pya.idFromName(var)).labels()]
                    if str(val) not in possible_states:
                        invalid_evidence.append(f"{var}={val} (valid: {possible_states})")
                else:
                    invalid_evidence.append(f"{var} (variable not found)")
                    
            if invalid_evidence:
                error_msg = f"Invalid evidence values: {', '.join(invalid_evidence[:2])}"
                if len(invalid_evidence) > 2:
                    error_msg += f" and {len(invalid_evidence) - 2} more"
                return html.Div(error_msg, style={'color': 'red'}), create_error_notification(
                    error_msg,
                    "Invalid Evidence"
                )
            
            try:
                posterior_array = bn_adapter.compute_posterior(evidence_dict, target_vars)
                domain = bn_adapter.get_domain_of(target_vars)
                probs_list = posterior_array.flatten().tolist()
                
                # Validate results
                if not probs_list or all(p == 0 for p in probs_list):
                    return html.Div("All probabilities are zero. Check your evidence values.", style={'color': 'red'}), create_warning_notification(
                        "All probabilities are zero. This might indicate impossible evidence.",
                        "Suspicious Results"
                    )
                
                # Create a DataFrame for better display
                df = pd.DataFrame({
                    'State': domain,
                    'Probability': [f"{p:.6f}" for p in probs_list]
                })
                table = dbc.Table.from_dataframe(df, bordered=True, striped=True, hover=True)
                
                result = dbc.Card(
                    dbc.CardBody([
                        html.H4("Compute Posterior", className="card-title"),
                        table
                    ]),
                    className="mt-3"
                )
                
                return result, None

            except ImplausibleEvidenceException:
                return html.Div("Impossible Evidence: The specified evidence combination is not possible in this network.", style={'color': 'red'}), create_error_notification(
                    "The specified evidence combination is impossible in this network. Please check your evidence values.",
                    "Impossible Evidence"
                )

        elif action == 'map_independence':
            logger.info(f"Computing MAP independence for targets: {target_vars}, evidence: {evidence_dict}, R: {r_vars}")
            
            try:
                map_result = bn_adapter.maximum_a_posteriori(evidence_dict, target_vars)
                map_dict, map_prob = map_result[0], map_result[1]
                
                # Validate MAP result
                if not map_dict:
                    return html.Div("No MAP assignment found.", style={'color': 'red'}), create_error_notification(
                        "No MAP assignment could be computed. Check your configuration.",
                        "MAP Computation Error"
                    )
                
                independence_bool = bn_adapter.map_independence(r_vars, evidence_dict, map_dict)

                if independence_bool:
                    result = dbc.Alert(
                        f"The MAP assignment {map_dict} is NOT altered by interventions on {r_vars} (INDEPENDENT).",
                        color="success",
                        className="mt-3"
                    )
                else:
                    result = dbc.Alert(
                        f"The MAP assignment {map_dict} IS altered by {r_vars} (DEPENDENT).",
                        color="primary",
                        className="mt-3"
                    )
                
                return result, None
                
            except ImplausibleEvidenceException:
                return html.Div("Impossible Evidence: The specified evidence combination is not possible in this network.", style={'color': 'red'}), create_error_notification(
                    "The specified evidence combination is impossible in this network.",
                    "Impossible Evidence"
                )

        elif action == 'defeaters':
            logger.info(f"Computing defeaters for targets: {target_vars}, evidence: {evidence_dict}")
            
            try:
                from probExplainer.algorithms.defeater import get_defeaters
                
                relevant_sets, irrelevant_sets = get_defeaters(
                    model=bn_adapter,
                    evidence=evidence_dict,
                    target=target_vars,
                    depth=float('inf'),
                    evaluate_singletons=True
                )
                
                # Validate results
                total_sets = len(relevant_sets) + len(irrelevant_sets)
                
                result = dbc.Card(
                    dbc.CardBody([
                        html.H4("Get Defeaters Results", className="card-title"),
                        html.H5("Relevant sets:", className="mt-3"),
                        html.Ul([html.Li(str(s)) for s in relevant_sets]) if relevant_sets else html.P("None"),
                        html.H5("Irrelevant sets:", className="mt-3"),
                        html.Ul([html.Li(str(s)) for s in irrelevant_sets]) if irrelevant_sets else html.P("None"),
                    ]),
                    className="mt-3"
                )
                
                return result, None

            except ImplausibleEvidenceException:
                return html.Div("Impossible Evidence: The specified evidence combination is not possible in this network.", style={'color': 'red'}), create_error_notification(
                    "The specified evidence combination is impossible in this network.",
                    "Impossible Evidence"
                )
            except ImportError:
                return html.Div("Defeaters algorithm not available. Please check ProbExplainer installation.", style={'color': 'red'}), create_error_notification(
                    "Defeaters algorithm not available. Please check ProbExplainer installation.",
                    "Algorithm Not Available"
                )

        else:
            return html.Div("Unknown action selected.", style={'color': 'red'}), create_error_notification(
                f"Unknown action: {action}",
                "Invalid Action"
            )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in {action}: {e}")
        
        # Provide specific error handling for common issues
        if "memory" in error_msg.lower() or "out of memory" in error_msg.lower():
            return html.Div("Out of memory. Try with a smaller network or fewer variables.", style={'color': 'red'}), create_error_notification(
                "Computation failed due to memory constraints. Try with fewer variables or a smaller network.",
                "Memory Error"
            )
        elif "timeout" in error_msg.lower():
            return html.Div("Computation timed out. Try with simpler parameters.", style={'color': 'red'}), create_error_notification(
                "Computation timed out. Try with simpler parameters or a smaller network.",
                "Timeout Error"
            )
        elif "convergence" in error_msg.lower():
            return html.Div("Algorithm did not converge. Results may be unreliable.", style={'color': 'red'}), create_error_notification(
                "Algorithm did not converge properly. Results may be unreliable.",
                "Convergence Error"
            )
        else:
            return html.Div(f"Error in {action}: {error_msg}", style={'color': 'red'}), create_error_notification(
                f"Error in {action}: {error_msg}",
                "Computation Error"
            )

# Callbacks for evidence selection buttons
@app.callback(
    Output({'type': 'evidence-checkbox', 'index': ALL}, 'value'),
    [Input('select-all-evidence', 'n_clicks'),
     Input('clear-evidence', 'n_clicks')],
    [State({'type': 'evidence-checkbox', 'index': ALL}, 'id')],
    prevent_initial_call=True
)
def update_evidence_selection(select_all_clicks, clear_clicks, checkbox_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'select-all-evidence':
        # Select all checkboxes
        return [[checkbox_id['index']] for checkbox_id in checkbox_ids]
    elif button_id == 'clear-evidence':
        # Clear all checkboxes
        return [[] for _ in checkbox_ids]
    
    raise PreventUpdate

# Callbacks for target selection buttons
@app.callback(
    Output({'type': 'target-checkbox', 'index': ALL}, 'value'),
    [Input('select-all-targets', 'n_clicks'),
     Input('clear-targets', 'n_clicks')],
    [State({'type': 'target-checkbox', 'index': ALL}, 'id')],
    prevent_initial_call=True
)
def update_target_selection(select_all_clicks, clear_clicks, checkbox_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'select-all-targets':
        # Select all checkboxes
        return [[checkbox_id['index']] for checkbox_id in checkbox_ids]
    elif button_id == 'clear-targets':
        # Clear all checkboxes
        return [[] for _ in checkbox_ids]
    
    raise PreventUpdate

# Callbacks for R variables selection buttons
@app.callback(
    Output({'type': 'r-vars-checkbox', 'index': ALL}, 'value'),
    [Input('select-all-r-vars', 'n_clicks'),
     Input('clear-r-vars', 'n_clicks')],
    [State({'type': 'r-vars-checkbox', 'index': ALL}, 'id')],
    prevent_initial_call=True
)
def update_r_vars_selection(select_all_clicks, clear_clicks, checkbox_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'select-all-r-vars':
        # Select all checkboxes
        return [[checkbox_id['index']] for checkbox_id in checkbox_ids]
    elif button_id == 'clear-r-vars':
        # Clear all checkboxes
        return [[] for _ in checkbox_ids]
    
    raise PreventUpdate

# Add callbacks for help popovers
@app.callback(
    Output("help-popover-evidence", "is_open"),
    Input("help-button-evidence", "n_clicks"),
    State("help-popover-evidence", "is_open")
)
def toggle_evidence_popover(n, is_open):
    if n:
        return not is_open
    return is_open

@app.callback(
    Output("help-popover-targets", "is_open"),
    Input("help-button-targets", "n_clicks"),
    State("help-popover-targets", "is_open")
)
def toggle_targets_popover(n, is_open):
    if n:
        return not is_open
    return is_open

@app.callback(
    Output("help-popover-r-vars", "is_open"),
    Input("help-button-r-vars", "n_clicks"),
    State("help-popover-r-vars", "is_open")
)
def toggle_r_vars_popover(n, is_open):
    if n:
        return not is_open
    return is_open

# Notification system callback
@app.callback(
    [Output('notification-container', 'children'),
     Output('notification-container', 'style')],
    Input('notification-store', 'data')
)
def show_notification(data):
    """Display notifications with Bootstrap toasts and animations"""
    if data is None:
        return None, {
            'position': 'fixed',
            'bottom': '20px',
            'right': '20px',
            'zIndex': '1000',
            'width': '300px',
            'transition': 'all 0.3s ease-in-out',
            'transform': 'translateY(100%)',
            'opacity': '0'
        }
    
    # Create toast with animation
    toast = dbc.Toast(
        data['message'],
        header=data['header'],
        icon=data['icon'],
        is_open=True,
        dismissable=True,
        style={
            'width': '100%',
            'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)',
            'borderRadius': '8px',
            'marginBottom': '10px'
        }
    )
    
    # Style to show notification with animation
    container_style = {
        'position': 'fixed',
        'bottom': '20px',
        'right': '20px',
        'zIndex': '1000',
        'width': '300px',
        'transition': 'all 0.3s ease-in-out',
        'transform': 'translateY(0)',
        'opacity': '1'
    }
    
    return toast, container_style

# Helper functions for creating notifications
def create_error_notification(message, header="Error"):
    """Create error notification data"""
    return {
        'message': message,
        'header': header,
        'icon': 'danger'
    }

def create_warning_notification(message, header="Warning"):
    """Create warning notification data"""
    return {
        'message': message,
        'header': header,
        'icon': 'warning'
    }

def create_info_notification(message, header="Info"):
    """Create info notification data"""
    return {
        'message': message,
        'header': header,
        'icon': 'info'
    }

# Setup session management callbacks
if SESSION_MANAGEMENT_AVAILABLE:
    @app.callback(
        Output('session-id-store', 'data'),
        Input('heartbeat-interval', 'n_intervals'),
        State('session-id-store', 'data'),
        prevent_initial_call=False
    )
    def initialize_session(n_intervals, stored_session_id):
        """Initialize session ID dynamically for each user."""
        if stored_session_id is None:
            # Create new session for this user
            session_manager = get_session_manager()
            new_session_id = session_manager.register_session()
            session_manager.register_process(new_session_id, os.getpid())
            logger.info(f"New PROBEXPLAINER session created: {new_session_id}")
            return new_session_id
        return stored_session_id
    
    @app.callback(
        Output('session-status', 'children'),
        Input('heartbeat-interval', 'n_intervals'),
        State('session-id-store', 'data'),
        prevent_initial_call=True
    )
    def send_heartbeat(n_intervals, session_id):
        """Send heartbeat to session manager."""
        if session_id:
            session_manager = get_session_manager()
            session_manager.heartbeat(session_id)
            if n_intervals % 12 == 0:  # Log every minute (every 12 intervals of 5s)
                logger.info(f"PROBEXPLAINER heartbeat sent for session: {session_id}")
            return f"Heartbeat sent: {n_intervals}"
        return "No session"
    
    @app.callback(
        Output('heartbeat-counter', 'data'),
        Input('cleanup-interval', 'n_intervals'),
        State('session-id-store', 'data'),
        prevent_initial_call=True
    )
    def periodic_cleanup_check(n_intervals, session_id):
        """Periodic check to ensure session is still active."""
        if session_id:
            session_manager = get_session_manager()
            active_sessions = session_manager.get_active_sessions()
            if session_id not in active_sessions:
                # Session expired, try to refresh or handle gracefully
                logger.warning(f"PROBEXPLAINER session {session_id} expired")
                return n_intervals
        return n_intervals

# ---------- (5) RUN THE SERVER ---------- #
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8054)