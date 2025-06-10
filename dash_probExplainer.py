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
import tempfile

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
    dcc.Loading(
        id="global-spinner",
        overlay_style={"visibility": "visible", "filter": "blur(1px)"},
        type="circle",
        fullscreen=False,
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
                dcc.Dropdown(
                    id='action-dropdown',
                    options=[
                        {'label': 'Compute Posterior', 'value': 'posterior'},
                        {'label': 'Map Independence', 'value': 'map_independence'},
                        {'label': 'Get Defeaters', 'value': 'defeaters'}
                    ],
                    value='posterior',  # Default action
                    style={'width': '50%', 'margin': '0 auto'}
                )
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
])


# ---------- (4) CALLBACKS ---------- #

# (A) Checking the "Use default" => set 'upload-data.contents'
@app.callback(
    Output('upload-data', 'contents'),
    Input('use-default-network', 'value'),
    prevent_initial_call=True
)
def use_default_dataset(value):
    """
    If 'default' is checked, read your local 'carwithnames.data' (or a default .bif) file,
    encode as base64, set upload-data.contents, triggering parse callback.
    
    NOTE: If 'carwithnames.data' is NOT a BIF, parsing will fail.
    """
    if 'default' in value:
        default_file = '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/Counterfactuals/carwithnames.data'
        try:
            with open(default_file, 'rb') as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode()
            return f"data:text/csv;base64,{b64}"
        except Exception as e:
            print(f"Error reading default dataset: {e}")
            return dash.no_update
    return dash.no_update


# (B) Store the chosen network (default or uploaded) in 'stored-network'
@app.callback(
    Output('stored-network', 'data'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    Input('use-default-network', 'value')
)
def load_network(contents, filename, default_value):
    """
    Store path/string in 'stored-network'.
    
    - If 'default' is in default_value => use the known path to network_5.bif (or your default).
    - If user uploads => decode the BIF string.
    - If nothing => PreventUpdate.
    """
    # If neither default is checked nor any file is uploaded => do nothing
    if (not contents) and ('default' not in default_value):
        raise PreventUpdate

    # If "Use default" is checked => always override with that
    if 'default' in default_value:
        logger.info("Using default network: network_5.bif")
        return {
            'network_name': 'network_5.bif',
            'network_type': 'path',
            # Adjust path to your real default BIF
            'content': '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/ProbExplainer/expert_networks/network_5.bif'
        }

    # Otherwise, if user uploaded something:
    if contents:
        logger.info(f"Attempting to load uploaded network: {filename}")
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            bif_data = decoded.decode('utf-8')
            # Check if valid BIF with pgmpy
            reader_check = BIFReader(string=bif_data)
            _ = reader_check.get_model()  # fails if invalid
            logger.info(f"Valid network uploaded: {filename}")
            return {
                'network_name': filename,
                'network_type': 'string',
                'content': bif_data
            }
        except Exception as e:
            logger.error(f"Error loading network: {e}")
            return dash.no_update

    raise PreventUpdate


# (C) Once 'stored-network' is set, parse it with pgmpy => store nodes/states in 'stored-model-info'
@app.callback(
    Output('stored-model-info', 'data'),
    Input('stored-network', 'data')
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

        # For each node, gather possible states:
        states_dict = {}
        for var in nodes_list:
            cpd = net.get_cpds(var)
            states_dict[var] = cpd.state_names[var]

        return {
            'nodes': nodes_list,
            'states': states_dict
        }
    except Exception as e:
        logger.error(f"Error parsing network in parse_network_and_store_info: {e}")
        return dash.no_update


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
                            dcc.Dropdown(
                                id={'type': 'evidence-value-dropdown', 'index': var},
                                options=[{'label': s, 'value': s} for s in var_states],
                                value=var_states[0] if var_states else None,
                                style={'width': '60%'}
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
    Input('run-action-button', 'n_clicks'),
    State('action-dropdown', 'value'),
    State('stored-network', 'data'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'value'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'id'),
    State({'type': 'target-checkbox', 'index': ALL}, 'value'),
    State({'type': 'r-vars-checkbox', 'index': ALL}, 'value')
)
def run_action(n_clicks, action, stored_network,
               evidence_values, evidence_ids,
               target_checkbox_values, r_vars_checkbox_values):
    if not n_clicks:
        raise PreventUpdate

    if not stored_network:
        return html.Div("No network loaded. Please upload or select the default network.", style={'color': 'red'})

    # Build evidence dict
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

    from probExplainer.model.BayesianNetwork import BayesianNetworkPyAgrum, ImplausibleEvidenceException

    # Load BN with pyAgrum (without loadBNFromString)
    try:
        if stored_network['network_type'] == 'path':
            bn_pya = gum.loadBN(stored_network['content'])
        else:
            # if it's a string => use our helper
            bn_pya = loadBNfromMemory(stored_network['content'])
    except Exception as e:
        return html.Div(f"Error loading network in pyAgrum: {e}", style={'color': 'red'})

    try:
        bn_adapter = BayesianNetworkPyAgrum(bn_pya)
    except Exception as e:
        return html.Div(f"Error creating BayesianNetworkPyAgrum: {e}", style={'color': 'red'})

    # Perform chosen action
    if action == 'posterior':
        if not target_vars:
            return html.Div("Please select at least one target variable for Compute Posterior.", style={'color': 'red'})
        try:
            posterior_array = bn_adapter.compute_posterior(evidence_dict, target_vars)
            domain = bn_adapter.get_domain_of(target_vars)
            probs_list = posterior_array.flatten().tolist()
            # Create a DataFrame for better display
            df = pd.DataFrame({
                'State': domain,
                'Probability': [f"{p:.6f}" for p in probs_list]
            })
            table = dbc.Table.from_dataframe(df, bordered=True, striped=True, hover=True)
            return dbc.Card(
                dbc.CardBody([
                    html.H4("Compute Posterior", className="card-title"),
                    table
                ]),
                className="mt-3"
            )

        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in compute_posterior: {e}", style={'color': 'red'})

    elif action == 'map_independence':
        if not target_vars:
            return html.Div("Please select at least one target variable for Map Independence.", style={'color': 'red'})
        if not r_vars:
            return html.Div("Please select at least one variable in R for Map Independence.", style={'color': 'red'})

        try:
            map_result = bn_adapter.maximum_a_posteriori(evidence_dict, target_vars)
            map_dict, map_prob = map_result[0], map_result[1]
            independence_bool = bn_adapter.map_independence(r_vars, evidence_dict, map_dict)

            if independence_bool:
                return dbc.Alert(
                    f"The MAP assignment {map_dict} is NOT altered by interventions on {r_vars} (INDEPENDENT).",
                    color="success",
                    className="mt-3"
                )
            else:
                return dbc.Alert(
                    f"The MAP assignment {map_dict} IS altered by {r_vars} (DEPENDENT).",
                    color="primary",
                    className="mt-3"
                )
        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in map_independence: {e}", style={'color': 'red'})

    elif action == 'defeaters':
        if not target_vars:
            return html.Div("Please select at least one target variable for Get Defeaters.", style={'color': 'red'})

        from probExplainer.algorithms.defeater import get_defeaters
        try:
            relevant_sets, irrelevant_sets = get_defeaters(
                model=bn_adapter,
                evidence=evidence_dict,
                target=target_vars,
                depth=float('inf'),
                evaluate_singletons=True
            )
            if not relevant_sets:
                relevant_str = "None"
            else:
                relevant_str = "\n".join(map(str, relevant_sets))
            if not irrelevant_sets:
                irrelevant_str = "None"
            else:
                irrelevant_str = "\n".join(map(str, irrelevant_sets))

            return dbc.Card(
                dbc.CardBody([
                    html.H4("Get Defeaters Results", className="card-title"),
                    html.H5("Relevant sets:", className="mt-3"),
                    html.Ul([html.Li(str(s)) for s in relevant_sets]) or html.P("None"),
                    html.H5("Irrelevant sets:", className="mt-3"),
                    html.Ul([html.Li(str(s)) for s in irrelevant_sets]) or html.P("None"),
                ]),
                className="mt-3"
            )

        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in get_defeaters: {e}", style={'color': 'red'})

    else:
        return html.Div("Unknown action.", style={'color': 'red'})

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

# ---------- (5) RUN THE SERVER ---------- #
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8054)