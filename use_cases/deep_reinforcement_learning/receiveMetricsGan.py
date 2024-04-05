import tail 
import threading
import pandas as pd
import numpy as np
from collections import deque
import datetime
from agent import DDQN
from environmentGan import ControlPlaneEnvironment
import os
import subprocess
import csv
from io import StringIO
import argparse
import time 

# Defining constants
TYPE_32 = 0
TYPE_64 = 1
FIRST_SECOND = 0
FOURTH_SECOND = -1
DEFAULT_QUEUE_SIZE = 64
DEFAULT_TARGET_DELAY = 50000


def sendtoRl(sample):
    """
    Processes and sends data samples to the reinforcement learning (RL) agent.

    Args:
        sample (DataFrame): A data sample containing INT and DASH states.

    Global Variables:
        ddqn (object): An instance of the Double Deep Q-Network (DDQN) class.
        env (object): An instance of the ControlPlaneEnvironment class.
        experiment_id (str): Unique identifier for the experiment.

    Returns:
        None: Data samples are processed and used for RL training.
    """
    global ddqn
    global env
    global experiment_id

    # Verify whether the agent has already taken actions
    if len(env.actions_history) == 0:
        # If not, determine the type of data sample (TYPE_32 or TYPE_64)
        # and retrieve the DataFrame from the global dictionary accordingly
        if list(sample).index(0) == TYPE_32:
            df_INT = sample[TYPE_32].iloc[:,:9]
            df_dash = sample[TYPE_32].iloc[:,9:12]
        else:
            df_INT = sample[TYPE_64].iloc[:,:9]
            df_dash = sample[TYPE_64].iloc[:,9:12]
    # If the agent has already taken actions, verify which action was taken
    # and retrieve the DataFrame from the global dictionary accordingly
    else:
        if env.actions_history[-1] == 0:
            df_INT = sample[TYPE_64].iloc[:,:9]
            df_dash = sample[TYPE_64].iloc[:,9:12]
        else:
            df_INT = sample[TYPE_32].iloc[:,:9]
            df_dash = sample[TYPE_32].iloc[:,9:12]

    # Convert data to numpy arrays
    current_state = df_INT.to_numpy()
    dash_state = df_dash.to_numpy()

    # Get state dimensionality
    state_dim = df_INT.shape[1]

    # Record training start time
    training_start = datetime.datetime.now()
    print("Received state, entering in the loop steps: {0}\n".format(training_start))

    # Choose an action using epsilon-greedy policy
    action = ddqn.epsilon_greedy_policy(current_state[FOURTH_SECOND].reshape(-1, state_dim))

    # Take the chosen action and observe the next state, reward, and done flag
    current_state, next_state, reward, done, _ = env.take_action(action, current_state, dash_state)
    print(reward)

    # If next state is available, memorize the transition and perform experience replay
    if next_state is not None:
        print("next state received, memorizing transition")

        ddqn.memorize_transition(current_state[FOURTH_SECOND],
                                env.actions_history[-2], # Action performed before reward calculation
                                reward,
                                next_state[FOURTH_SECOND],
                                0.0 if done else 1.0)

        if ddqn.train:
            ddqn.experience_replay()
    
    # Record training end time
    training_end = datetime.datetime.now()
    print("Exiting the loop steps: {0}".format(training_end))

    # Print information about the last action taken, the corresponding reward, the frames per second (FPS),
    # and the switches queue size
    print("\n========================================\n")
    print("last action: {0} | reward: {1} | fps: {2} | "
          "Buffer size: {3}".format(
           env.actions_history[-1], env.reward_history[-1],
           env.fps_history[-1], env.buffer_size[-1]))
    print("\n========================================\n")

    # Save training logs (action history, reward history, FPS history, LBO history, losses, and Q-values)
    save_training_logs(env, ddqn, experiment_id)

    # Save the trained agent's state
    ddqn.save_agent(experiment_id)


def jointoRL(sample, t):
    """
    Joins data samples processed by the "readFile32" and "readFile64" functions based on the specified type 't'.

    Args:
        sample (DataFrame): A data sample.
        t (str): Type identifier.
    
    Global Variables:
        sampleJoin (dict): A global dictionary to store DataFrames representing the environment state for both
                           32 bit and 64 bit queue sizes.

    Returns:
        None: Processed data is sent to 'sendtoRl' to enable the agent-environment interaction.
    """
    global sampleJoin

    # Store the data sample in the global dictionary using the specified type 't'
    sampleJoin[t] = sample
    
    # If two data samples have been collected (INT and DASH metrics related to the 32 bit and 64 bit queue sizes),
    # call the 'sendtoRl' function
    if len(sampleJoin) == 2:
        sendtoRl(sampleJoin)


def readFile32():
    """
    Reads the synthetic data generated by TimeGAN for INT and DASH states related to the 32 bit queue size.

    Global Variables:
        sample32 (DataFrame): A global DataFrame to store processed data.

    Returns:
        None: 'sample32' is sent to jointoRL to be further processed.
    """
    global sample32
    
    # Define the columns of interest
    cols = ['enq_qdepth1',
            'deq_timedelta1',
            'deq_qdepth1',
            ' enq_qdepth2',
            ' deq_timedelta2',
            ' deq_qdepth2',
            'enq_qdepth3',
            'deq_timedelta3',
            'deq_qdepth3',
            'FPS',
            'Buffer',
            'CalcBitrate',
            'ReportedBitrate',
            'q_size']

    # Read the CSV file in chunks of 4 seconds
    for sample32 in pd.read_csv('gan/best_modelsum_32.csv', chunksize=4):
        # Select only the specified columns
        sample32 = sample32[cols]
        # Process the data using the 'jointoRL' function with TYPE_64
        jointoRL(sample32, TYPE_32)


def readFile64():
    """
    Reads the synthetic data generated by TimeGAN for INT and DASH states related to the 64 bit queue size.

    Global Variables:
        sample64 (DataFrame): A global DataFrame to store processed data.
        experiment_start (datetime): Timestamp when the experiment starts.

    Returns:
        None: 'sample64' is sent to jointoRL to be further processed.
    """
    global sample64
    global experiment_start 
    
    # Define the columns of interest
    cols = ['enq_qdepth1',
            'deq_timedelta1',
            'deq_qdepth1',
            ' enq_qdepth2',
            ' deq_timedelta2',
            ' deq_qdepth2',
            'enq_qdepth3',
            'deq_timedelta3',
            'deq_qdepth3',
            'FPS',
            'Buffer',
            'CalcBitrate',
            'ReportedBitrate',
            'q_size']

    # Read the CSV file in chunks of 4 seconds
    for sample64 in pd.read_csv('gan/best_modelsum_64.csv', chunksize=4):
        # Select only the specified columns
        sample64 = sample64[cols]
        # Process the data using the 'jointoRL' function with TYPE_64
        jointoRL(sample64, TYPE_64)
    
    # Calculate experiment duration
    experiment_end = datetime.datetime.now()
    time_difference = experiment_end - experiment_start

    # Print experiment duration
    print("\n==========================================================\n")
    print("Experiment time (in seconds): {0}".format(time_difference.total_seconds()))
    print("Experiment time (in minutes): {0}".format(time_difference.total_seconds() / 60))
    print("\n==========================================================\n")


def instantiateDQN():
    """
    Instantiates a Double Deep Q-Network (DDQN) agent with specified hyperparameters.

    Returns:
        object: An instance of the DDQN class.
    """

    # Discount factor
    gamma = .99
    # Target network update frequency.
    tau = 10000
    
    # Units per layer in the neural network
    architecture = (24, 24)
    # Learning rate (default 1e-3)
    learning_rate = 1e-3
    # L2 regularization
    l2_reg = 1e-6            
    
    # Capacity of the replay buffer
    replay_capacity = int(1e6)
    # Batch size for training
    batch_size = 32
    # Minimum experience memory before training starts
    minimum_experience_memory = 100 
    
    # Initial exploration rate (epsilon-greedy)
    epsilon_start = 1.0
    # Final exploration rate
    epsilon_end = .01
    # Number of steps for epsilon decay (default 250)
    epsilon_decay_steps = 250
    # Exponential decay factor for epsilon
    epsilon_exponential_decay = .99

    # Number of possible actions
    num_actions = 2
    # Dimensionality of the state (INT features)
    state_dim = 9
    
    # Weight initialization method ('standard' or 'pretrained')
    initialization='standard'
    # Experiment type: 1 - train the DQN, 2 - inference only,
    # 3 - transfer learning with weight freezing (not working as expected)
    experiment_type = 1 

    # Filepath for loading the online network pretrained weights
    online_network_filepath=''
    # Filepath for loading the target network pretrained weights
    target_network_filepath=''

    # Create an instance of the DDQN class
    ddqn = DDQN(state_dim=state_dim,
                num_actions=num_actions,
                learning_rate=learning_rate,
                gamma=gamma,
                epsilon_start=epsilon_start,
                epsilon_end=epsilon_end,
                epsilon_decay_steps=epsilon_decay_steps,
                epsilon_exponential_decay=epsilon_exponential_decay,
                replay_capacity=replay_capacity,
                architecture=architecture,
                l2_reg=l2_reg,
                tau=tau,
                batch_size=batch_size,
                minimum_experience_memory=minimum_experience_memory,
                initialization=initialization,
                online_network_filepath=online_network_filepath,
                target_network_filepath=target_network_filepath,
                experiment_type=experiment_type)

    # Return an instance of the DDQN class
    return ddqn


def save_training_logs(environment, agent, experiment_id):
    """
    Saves the agent training logs to CSV files.

    Args:
        environment (object): An instance of the environment class.
        agent (object): An instance of the agent class.
        experiment_id (str): Unique identifier for the experiment.

    Returns:
        None: Logs are saved in separate CSV files.
    """
    
    # Save action history
    with open('agent_logs/action_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.actions_history))

    # Save reward history
    with open('agent_logs/reward_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.reward_history))
    
    # Save FPS history
    with open('agent_logs/fps_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.fps_history))
    
    # Save LBO history
    with open('agent_logs/lbo_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], environment.lbo_history))
    
    # Save loss history
    with open('agent_logs/loss_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], agent.losses))
    
    # Save Q-values history
    with open('agent_logs/q-values_history_{0}.csv'.format(experiment_id), 'w+', newline ='') as file:
        writer = csv.writer(file)
        writer.writerows(map(lambda x: [x], agent.q_values))


def main():
    """
    Entry point for the experiment execution.

    Global Variables:
        sampleJoin (dict): A global dictionary.
        count (int): A global counter.
        ddqn (object): An instance of the DQN class.
        env (object): An instance of the ControlPlaneEnvironment class.
        experiment_id (str): Unique identifier for the experiment.
        experiment_start (datetime): Timestamp when the experiment starts.

    Command Line Arguments:
        number (str): Number of executions.
        type (str): Type of experiment (TD, iRED, iRED-RL).

    Returns:
        None: Logs are saved after the experiment.
    """

    # Defining global variables
    global sampleJoin
    global count
    global ddqn
    global env
    global experiment_id
    global experiment_start 

    # Initialize experiment start timestamp
    experiment_start = datetime.datetime.now()

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Experiment execution",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument("number", type=str, help="Number of executions")
    parser.add_argument("type", type=str, help="TD, iRED, iRED-RL")
    
    args = parser.parse_args()
    config = vars(args)
    
    # Create a unique experiment ID
    experiment_id = config['type']+"_"+config['number']

    # Set numpy print options
    np.set_printoptions(precision=2)

    # Initializing the global variables
    count = 0
    sampleJoin = dict()
    ddqn = instantiateDQN()
    env = ControlPlaneEnvironment()
    
    # Start reading files in separate threads
    thread64 = threading.Thread(target=readFile64)
    thread64.start()

    thread32 = threading.Thread(target=readFile32)
    thread32.start()
    
    # Sleep for 180 seconds (3 minutes)
    time.sleep(180)

    # Save the agent's state
    ddqn.save_agent(experiment_id)
    print("logs saved")
     

if __name__ == '__main__':
    """
    Entry point for the script execution.

    This block of code ensures that the 'main()' function is executed only when this script is run directly,
    not when it is imported as a module in another script.

    Returns:
        None: The 'main()' function is called.
    """
    main()
