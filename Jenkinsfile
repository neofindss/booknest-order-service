pipeline {
    agent any

    environment {
        IMAGE_NAME = 'booknest-order'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Test') {
            steps {
                sh 'python3 -m pip install -r requirements.txt'
                sh 'python3 -m pytest -q'
            }
        }
        stage('Build image') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} ."
            }
        }
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh "kubectl -n booknest set image deployment/order-service order=${IMAGE_NAME}:${BUILD_NUMBER}"
                sh 'kubectl -n booknest rollout status deployment/order-service --timeout=180s'
            }
        }
    }
}
