pipeline {
    agent {
      label 'av'
    }

    environment {
      GITHUB_TOKEN = credentials('av-github-token')
    }
    stages {
        stage('Notify Github about pending job') {
            steps {
                sh '''
                  set +x
                  curl "https://api.github.com/repos/vrk-kpa/opendata/statuses/$GIT_COMMIT?access_token=$GITHUB_TOKEN" \
                    -H "Content-Type: application/json" \
                    -X POST \
                    -d "{\"state\": \"pending\", \"description\": \"Jenkins\", \"target_url\": \"http://http://vrk-jenkins.eden.csc.fi/job/av/job/av-run-ansible/$BUILD_NUMBER/console\"}"
                '''
            }
        }
        stage('Run ansible') {
            steps {
                echo 'Running ansible...'
            }
        }
        stage('Notify Github about finished job') {
            steps {
              sh '''
                set +x
                echo $BUILD_STATUS

                if [ $BUILD_STATUS == 'success' ]
                then
                  export STATUS="success"
                else
                  export STATUS="failure"
                fi


                curl "https://api.github.com/repos/vrk-kpa/opendata/statuses/$GIT_COMMIT?access_token=$GITHUB_TOKEN" \
                  -H "Content-Type: application/json" \
                  -X POST \
                  -d "{\"state\": \"$STATUS\", \"description\": \"VRK Jenkins\", \"target_url\": \"http://vrk-jenkins.eden.csc.fi/job/av/job/av-run-ansible/$BUILD_NUMBER/console\"}"
              '''
            }
        }
    }
}
